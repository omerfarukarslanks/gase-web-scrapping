import { Player } from '@remotion/player';
import { ArrowLeft, Film, RefreshCw, Wand2 } from 'lucide-react';
import { startTransition, useDeferredValue, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { readRemotionPayload, SAMPLE_REMOTION_PAYLOAD, saveRemotionPayload, parseRemotionPayload } from '../lib/remotionPayload';
import { PromptVideo } from '../remotion/PromptVideo';

const FPS = 30;

export default function RemotionPreviewPage() {
  const initialPayload = readRemotionPayload() ?? SAMPLE_REMOTION_PAYLOAD;
  const [jsonInput, setJsonInput] = useState(JSON.stringify(initialPayload, null, 2));
  const [payload, setPayload] = useState(initialPayload);
  const [error, setError] = useState<string | null>(null);
  const deferredPayload = useDeferredValue(payload);

  const durationInFrames = useMemo(
    () => Math.max(FPS * 8, deferredPayload.durationSeconds * FPS),
    [deferredPayload.durationSeconds]
  );

  const handleApply = () => {
    try {
      const nextPayload = parseRemotionPayload(JSON.parse(jsonInput));
      setError(null);
      saveRemotionPayload(nextPayload);
      startTransition(() => {
        setPayload(nextPayload);
      });
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'JSON parse edilemedi.');
    }
  };

  const handleReloadSaved = () => {
    const saved = readRemotionPayload();
    const nextPayload = saved ?? SAMPLE_REMOTION_PAYLOAD;
    setJsonInput(JSON.stringify(nextPayload, null, 2));
    setPayload(nextPayload);
    setError(null);
  };

  return (
    <div className="grid gap-8 xl:grid-cols-[0.92fr_1.08fr]">
      <section className="space-y-6">
        <div className="rounded-[32px] bg-slate-950 px-7 py-8 text-white shadow-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-300">Remotion Preview</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight">JSON promptu videoya cevir ve onizle</h2>
          <p className="mt-4 text-sm leading-7 text-slate-300">
            Buradaki JSON artik iki katman tasir: insan okunur creative brief ve AI tarafindan karar verilmis video
            plan. Player, bu planin viewer-facing icerigini ekranda canlandirir.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/prompts"
              className="inline-flex items-center gap-2 rounded-2xl bg-white/10 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/15"
            >
              <ArrowLeft className="h-4 w-4" />
              Prompt Library
            </Link>
            <button
              onClick={handleReloadSaved}
              className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
            >
              <RefreshCw className="h-4 w-4" />
              Secili Promptu Yukle
            </button>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Prompt JSON</p>
              <h3 className="mt-1 text-lg font-semibold text-slate-900">Remotion input payload</h3>
            </div>
            <button
              onClick={handleApply}
              className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
            >
              <Wand2 className="h-4 w-4" />
              JSON'u Uygula
            </button>
          </div>

          <textarea
            value={jsonInput}
            onChange={(event) => setJsonInput(event.target.value)}
            spellCheck={false}
            className="mt-4 h-[520px] w-full rounded-2xl border border-slate-200 bg-slate-950 p-4 font-mono text-sm leading-6 text-slate-100 outline-none transition focus:border-blue-500"
          />

          {error ? (
            <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
          ) : (
            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              JSON gecerli. Guncel payload oyuncuya aktarilmaya hazir.
            </div>
          )}
        </div>
      </section>

      <section className="space-y-6">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Video Output</p>
              <h3 className="mt-1 text-lg font-semibold text-slate-900">{payload.headline}</h3>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              <Film className="h-4 w-4" />
              {payload.durationSeconds}s preview
            </div>
          </div>

          <div className="overflow-hidden rounded-[28px] border border-slate-200 bg-slate-950">
            <Player
              component={PromptVideo}
              inputProps={{ payload: deferredPayload }}
              durationInFrames={durationInFrames}
              compositionWidth={1280}
              compositionHeight={720}
              fps={FPS}
              controls
              style={{ width: '100%', aspectRatio: '16 / 9' }}
            />
          </div>

          <div className="mt-5 flex flex-wrap gap-2 text-xs text-slate-500">
            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 font-semibold">
              {payload.videoPlan.duration_seconds}s
            </span>
            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 font-semibold">
              {payload.videoPlan.scenes.length} scene{payload.videoPlan.scenes.length > 1 ? 's' : ''}
            </span>
            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 font-semibold">
              {payload.videoPlan.pacing_hint}
            </span>
            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 font-semibold">
              {payload.visualAssets.length} visual asset{payload.visualAssets.length !== 1 ? 's' : ''}
            </span>
          </div>

          <details className="mt-5 rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4">
            <summary className="cursor-pointer list-none text-sm font-semibold text-slate-800">
              Creative Brief
            </summary>
            <p className="mt-3 text-sm leading-7 text-slate-700">{payload.promptText}</p>
          </details>

          <details className="mt-4 rounded-3xl border border-slate-200 bg-slate-950 px-5 py-4 text-white">
            <summary className="cursor-pointer list-none text-sm font-semibold text-white">
              Video Plan
            </summary>
            <div className="mt-4 space-y-3">
              {payload.videoPlan.scenes.map((scene) => (
                <div key={scene.scene_id} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                      {scene.purpose}
                    </p>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                      {scene.layout_hint} · {scene.duration_seconds}s
                    </p>
                  </div>
                  <p className="mt-2 text-sm font-semibold text-white">{scene.headline}</p>
                  {scene.body ? <p className="mt-1 text-sm leading-6 text-slate-300">{scene.body}</p> : null}
                </div>
              ))}
            </div>
          </details>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Preview notlari</p>
          <div className="mt-4 grid gap-3 text-sm text-slate-600">
            <p>Bu ekran secili promptu Remotion Player ile canli video akisina cevirir.</p>
            <p>`promptText` insan okunur yaratıcı katmandir; `videoPlan.scenes` ise AI tarafindan karar verilmis master-video akisidir.</p>
            <p>Bir sonraki adimda istersen ayni payload'i gercek MP4 render pipeline'ina baglayabiliriz.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
