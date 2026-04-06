/**
 * Remotion Renderer Service
 *
 * POST /render  — renders a PromptVideo composition to MP4
 * GET  /health  — health check
 */

import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import express from 'express';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PORT = parseInt(process.env.PORT ?? '3001', 10);

// Path to the Remotion entry file inside the mounted frontend source
const ENTRY_FILE = process.env.REMOTION_ENTRY ?? '/frontend/src/remotion/entry.tsx';

// Output directory (shared volume with API container)
const OUTPUT_DIR = process.env.OUTPUT_DIR ?? '/app/static/videos';

// API base URL so we can resolve relative /static/... URLs to absolute ones
const API_BASE_URL = process.env.API_BASE_URL ?? 'http://api:8000';

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

// Bundle is built once at startup and reused for all renders
let bundleLocation = null;

// Path to the frontend's node_modules (for resolving imports like lucide-react, etc.)
const FRONTEND_NODE_MODULES = process.env.FRONTEND_NODE_MODULES ?? '/frontend/node_modules';

async function getBundle() {
  if (bundleLocation) return bundleLocation;

  console.log('[renderer] Bundling Remotion entry:', ENTRY_FILE);
  bundleLocation = await bundle({
    entryPoint: ENTRY_FILE,
    webpackOverride: (config) => {
      // Add the frontend's node_modules to the module resolution path
      // so PromptVideo's imports (lucide-react, react-router-dom, etc.) resolve correctly
      config.resolve = config.resolve ?? {};
      config.resolve.modules = [
        FRONTEND_NODE_MODULES,
        path.resolve(__dirname, 'node_modules'),
        'node_modules',
        ...(config.resolve.modules ?? []),
      ];
      // Use the frontend tsconfig
      config.resolve.plugins = config.resolve.plugins ?? [];
      return config;
    },
  });
  console.log('[renderer] Bundle ready:', bundleLocation);
  return bundleLocation;
}

// ---------------------------------------------------------------------------
// Express app
// ---------------------------------------------------------------------------

const app = express();
app.use(express.json({ limit: '10mb' }));

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', bundleReady: bundleLocation !== null });
});

app.post('/render', async (req, res) => {
  let {
    payload,
    audioUrl,
    durationInFrames = 900,
    fps = 30,
    width = 1080,
    height = 1920,
    outputFilename,
  } = req.body;

  // Resolve relative /static/... URLs to absolute so Remotion can fetch them
  if (audioUrl && audioUrl.startsWith('/')) {
    audioUrl = `${API_BASE_URL}${audioUrl}`;
  }
  // Also resolve image URLs inside visualAssets
  if (payload?.visualAssets) {
    payload = {
      ...payload,
      visualAssets: payload.visualAssets.map((asset) => ({
        ...asset,
        url: asset.url?.startsWith('/') ? `${API_BASE_URL}${asset.url}` : asset.url,
      })),
    };
  }

  if (!payload) {
    return res.status(400).json({ error: 'payload gerekli' });
  }
  if (!outputFilename) {
    return res.status(400).json({ error: 'outputFilename gerekli' });
  }

  const outputPath = path.join(OUTPUT_DIR, outputFilename);

  console.log(`[renderer] Render başlatılıyor: ${outputFilename} (${durationInFrames} frames @ ${fps}fps, ${width}x${height})`);

  try {
    const bundleLoc = await getBundle();

    const composition = await selectComposition({
      serveUrl: bundleLoc,
      id: 'PromptVideo',
      inputProps: { payload, audioUrl },
    });

    // Override calculated dimensions/duration from request
    composition.durationInFrames = durationInFrames;
    composition.fps = fps;
    composition.width = width;
    composition.height = height;

    await renderMedia({
      composition,
      serveUrl: bundleLoc,
      codec: 'h264',
      outputLocation: outputPath,
      inputProps: { payload, audioUrl },
      chromiumOptions: {
        disableWebSecurity: true,
        headless: true,
      },
      // Allow remote URLs (SDXL images, audio)
      offthreadVideoCacheSizeInBytes: 128 * 1024 * 1024,
    });

    const durationSeconds = durationInFrames / fps;
    console.log(`[renderer] Render tamamlandı: ${outputFilename} (${durationSeconds.toFixed(1)}s)`);

    return res.json({
      outputFilename,
      durationSeconds,
    });
  } catch (err) {
    console.error('[renderer] Render başarısız:', err);
    // Clean up incomplete file
    try { fs.unlinkSync(outputPath); } catch {}
    return res.status(500).json({ error: String(err?.message ?? err) });
  }
});

// Pre-warm bundle at startup so first render is faster
app.listen(PORT, async () => {
  console.log(`[renderer] Listening on :${PORT}`);
  try {
    await getBundle();
  } catch (err) {
    console.error('[renderer] Bundle ön-yükleme başarısız (ilk render\'da tekrar denenecek):', err?.message ?? err);
    bundleLocation = null;
  }
});
