import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type { ReactNode } from 'react';
import type {
  LayoutFamily,
  RemotionPromptPayload,
  VideoPlanLayoutHint,
  VideoPlanScene,
  VisualAsset,
} from '../types/analysis';

type Theme = {
  accent: string;
  glow: string;
  bg: string;
  gradientStart: string;
  gradientEnd: string;
  panel: string;
  panelStrong: string;
  ink: string;
  softInk: string;
  line: string;
};

type CanvasMetrics = {
  width: number;
  height: number;
  isVertical: boolean;
  paddingX: number;
  paddingTop: number;
  paddingBottom: number;
};

const categoryThemes: Record<string, Theme> = {
  politics: {
    accent: '#ef4444',
    glow: 'rgba(239,68,68,0.18)',
    bg: '#24090d',
    gradientStart: '#431018',
    gradientEnd: '#150306',
    panel: 'rgba(51, 15, 20, 0.72)',
    panelStrong: 'rgba(90, 22, 30, 0.92)',
    ink: '#fff1f2',
    softInk: 'rgba(255,228,230,0.86)',
    line: 'rgba(248,113,113,0.24)',
  },
  business: {
    accent: '#14b8a6',
    glow: 'rgba(20,184,166,0.22)',
    bg: '#051b1a',
    gradientStart: '#062c2a',
    gradientEnd: '#020e0d',
    panel: 'rgba(12, 33, 31, 0.72)',
    panelStrong: 'rgba(16, 53, 49, 0.92)',
    ink: '#f8fafc',
    softInk: 'rgba(226,232,240,0.86)',
    line: 'rgba(45,212,191,0.26)',
  },
  economy: {
    accent: '#10b981',
    glow: 'rgba(16,185,129,0.2)',
    bg: '#051a14',
    gradientStart: '#083124',
    gradientEnd: '#030d0a',
    panel: 'rgba(11, 36, 28, 0.72)',
    panelStrong: 'rgba(14, 64, 48, 0.92)',
    ink: '#ecfdf5',
    softInk: 'rgba(209,250,229,0.86)',
    line: 'rgba(52,211,153,0.24)',
  },
  world: {
    accent: '#3b82f6',
    glow: 'rgba(59,130,246,0.2)',
    bg: '#07162d',
    gradientStart: '#0c2451',
    gradientEnd: '#030a18',
    panel: 'rgba(10, 26, 52, 0.72)',
    panelStrong: 'rgba(17, 45, 87, 0.92)',
    ink: '#eff6ff',
    softInk: 'rgba(219,234,254,0.88)',
    line: 'rgba(96,165,250,0.24)',
  },
  science: {
    accent: '#22d3ee',
    glow: 'rgba(34,211,238,0.2)',
    bg: '#041822',
    gradientStart: '#062e3d',
    gradientEnd: '#020c12',
    panel: 'rgba(7, 33, 46, 0.72)',
    panelStrong: 'rgba(9, 54, 76, 0.92)',
    ink: '#ecfeff',
    softInk: 'rgba(207,250,254,0.86)',
    line: 'rgba(103,232,249,0.24)',
  },
  environment: {
    accent: '#84cc16',
    glow: 'rgba(132,204,22,0.18)',
    bg: '#101c05',
    gradientStart: '#23380d',
    gradientEnd: '#070d02',
    panel: 'rgba(28, 43, 10, 0.72)',
    panelStrong: 'rgba(53, 84, 13, 0.92)',
    ink: '#f7fee7',
    softInk: 'rgba(236,252,203,0.86)',
    line: 'rgba(163,230,53,0.26)',
  },
  health: {
    accent: '#06b6d4',
    glow: 'rgba(6,182,212,0.18)',
    bg: '#061820',
    gradientStart: '#0a2f3b',
    gradientEnd: '#020b10',
    panel: 'rgba(10, 33, 42, 0.72)',
    panelStrong: 'rgba(14, 62, 79, 0.92)',
    ink: '#ecfeff',
    softInk: 'rgba(207,250,254,0.86)',
    line: 'rgba(103,232,249,0.24)',
  },
  sports: {
    accent: '#f97316',
    glow: 'rgba(249,115,22,0.22)',
    bg: '#240e05',
    gradientStart: '#3d1808',
    gradientEnd: '#120703',
    panel: 'rgba(44, 20, 7, 0.72)',
    panelStrong: 'rgba(93, 33, 5, 0.92)',
    ink: '#fff7ed',
    softInk: 'rgba(255,237,213,0.88)',
    line: 'rgba(251,146,60,0.28)',
  },
  culture: {
    accent: '#ec4899',
    glow: 'rgba(236,72,153,0.18)',
    bg: '#240816',
    gradientStart: '#4a102c',
    gradientEnd: '#13030a',
    panel: 'rgba(51, 13, 31, 0.72)',
    panelStrong: 'rgba(87, 20, 53, 0.92)',
    ink: '#fdf2f8',
    softInk: 'rgba(252,231,243,0.86)',
    line: 'rgba(244,114,182,0.24)',
  },
  arts: {
    accent: '#f59e0b',
    glow: 'rgba(245,158,11,0.18)',
    bg: '#241507',
    gradientStart: '#4a2808',
    gradientEnd: '#120803',
    panel: 'rgba(47, 28, 10, 0.72)',
    panelStrong: 'rgba(92, 52, 12, 0.92)',
    ink: '#fffbeb',
    softInk: 'rgba(254,243,199,0.86)',
    line: 'rgba(251,191,36,0.26)',
  },
  technology: {
    accent: '#8b5cf6',
    glow: 'rgba(139,92,246,0.2)',
    bg: '#150a29',
    gradientStart: '#231242',
    gradientEnd: '#0a0515',
    panel: 'rgba(31, 17, 53, 0.72)',
    panelStrong: 'rgba(59, 32, 102, 0.92)',
    ink: '#f5f3ff',
    softInk: 'rgba(237,233,254,0.86)',
    line: 'rgba(167,139,250,0.26)',
  },
  opinion: {
    accent: '#e879f9',
    glow: 'rgba(232,121,249,0.18)',
    bg: '#1f0a24',
    gradientStart: '#35103f',
    gradientEnd: '#100412',
    panel: 'rgba(43, 13, 50, 0.72)',
    panelStrong: 'rgba(74, 22, 86, 0.92)',
    ink: '#fdf4ff',
    softInk: 'rgba(250,232,255,0.86)',
    line: 'rgba(240,171,252,0.24)',
  },
  analysis: {
    accent: '#a78bfa',
    glow: 'rgba(167,139,250,0.18)',
    bg: '#130c26',
    gradientStart: '#231445',
    gradientEnd: '#090510',
    panel: 'rgba(31, 18, 55, 0.72)',
    panelStrong: 'rgba(52, 31, 94, 0.92)',
    ink: '#f5f3ff',
    softInk: 'rgba(237,233,254,0.86)',
    line: 'rgba(196,181,253,0.24)',
  },
  general: {
    accent: '#38bdf8',
    glow: 'rgba(56,189,248,0.18)',
    bg: '#081421',
    gradientStart: '#0e2236',
    gradientEnd: '#040a11',
    panel: 'rgba(12, 25, 39, 0.72)',
    panelStrong: 'rgba(17, 39, 64, 0.92)',
    ink: '#f8fafc',
    softInk: 'rgba(226,232,240,0.86)',
    line: 'rgba(125,211,252,0.24)',
  },
};

function clamp<T>(items: T[], max: number): T[] {
  return items.slice(0, max);
}

function uniqueText(items: Array<string | null | undefined>): string[] {
  return Array.from(new Set(items.map((item) => item?.trim() ?? '').filter(Boolean)));
}

function formatPlannerLabel(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function useReveal(delay = 0) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const reveal = spring({
    fps,
    frame: Math.max(0, frame - delay),
    config: { damping: 16, stiffness: 90 },
  });

  return {
    opacity: interpolate(reveal, [0, 1], [0, 1]),
    translateY: interpolate(reveal, [0, 1], [24, 0]),
    translateX: interpolate(reveal, [0, 1], [24, 0]),
    scale: interpolate(reveal, [0, 1], [0.96, 1]),
  };
}

function useCanvasMetrics(): CanvasMetrics {
  const { width, height } = useVideoConfig();
  const isVertical = height > width;

  return {
    width,
    height,
    isVertical,
    paddingX: isVertical ? 54 : 56,
    paddingTop: isVertical ? 118 : 48,
    paddingBottom: isVertical ? 84 : 48,
  };
}

function CategoryBadge({ category, theme }: { category: string; theme: Theme }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 18px',
        borderRadius: 999,
        background: `${theme.accent}24`,
        border: `1px solid ${theme.line}`,
      }}
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: 999,
          background: theme.accent,
          boxShadow: `0 0 24px ${theme.accent}`,
        }}
      />
      <span
        style={{
          color: theme.ink,
          fontSize: 16,
          fontWeight: 800,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}
      >
        {category}
      </span>
    </div>
  );
}

function Chip({ label, theme }: { label: string; theme: Theme }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '10px 18px',
        borderRadius: 999,
        background: `${theme.accent}1a`,
        border: `1px solid ${theme.line}`,
        color: theme.ink,
        fontSize: 16,
        fontWeight: 650,
        letterSpacing: '0.02em',
      }}
    >
      {label}
    </span>
  );
}

function SourceLine({ value, theme }: { value: string; theme: Theme }) {
  if (!value) return null;
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 34,
        left: 60,
        right: 60,
        textAlign: 'center',
        color: theme.softInk,
        fontSize: 14,
        fontWeight: 600,
        letterSpacing: '0.04em',
        opacity: 0.72,
      }}
    >
      {value}
    </div>
  );
}

function BackgroundMotif({ theme, frame }: { theme: Theme; frame: number }) {
  const drift = frame * 0.5;
  return (
    <>
      <div
        style={{
          position: 'absolute',
          inset: -160,
          background: `radial-gradient(ellipse at 30% 20%, ${theme.glow}, transparent 50%), radial-gradient(ellipse at 70% 80%, rgba(255,255,255,0.03), transparent 40%), linear-gradient(155deg, ${theme.gradientStart} 0%, ${theme.bg} 40%, ${theme.gradientEnd} 100%)`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: -60 + drift * 0.3,
          top: 180,
          width: 340,
          height: 340,
          borderRadius: 999,
          border: `1px solid ${theme.line}`,
          opacity: 0.2,
        }}
      />
      <div
        style={{
          position: 'absolute',
          right: 60,
          bottom: 100 - drift * 0.2,
          width: 280,
          height: 280,
          borderRadius: 999,
          border: `1px solid ${theme.line}`,
          opacity: 0.15,
        }}
      />
    </>
  );
}

function pickSceneAsset(scene: VideoPlanScene, assets: VisualAsset[]): VisualAsset | null {
  const preferredIds = scene.asset_ids ?? [];
  for (const assetId of preferredIds) {
    const match = assets.find((asset) => asset.asset_id === assetId);
    if (match) return match;
  }
  return assets[0] ?? null;
}

function SceneBackdrop({
  asset,
  theme,
  frame,
  isVertical,
}: {
  asset: VisualAsset | null;
  theme: Theme;
  frame: number;
  isVertical: boolean;
}) {
  if (!asset) {
    return <BackgroundMotif theme={theme} frame={frame} />;
  }

  const scale = 1.04 + frame * 0.00055;
  const translateY = Math.sin(frame / 28) * 8;

  return (
    <>
      <div
        style={{
          position: 'absolute',
          inset: -40,
          overflow: 'hidden',
        }}
      >
        <img
          src={asset.url}
          alt={asset.alt_text}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: isVertical ? 'center 12%' : 'center 18%',
            transform: `translate3d(0, ${translateY}px, 0) scale(${scale})`,
            filter: 'brightness(0.62) saturate(1.02) contrast(1.04)',
          }}
        />
      </div>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: isVertical
            ? `linear-gradient(180deg, rgba(2,6,23,0.12) 0%, rgba(2,6,23,0.24) 20%, rgba(2,6,23,0.58) 52%, ${theme.bg}f1 100%)`
            : `linear-gradient(180deg, rgba(2,6,23,0.1) 0%, rgba(2,6,23,0.22) 18%, rgba(2,6,23,0.48) 58%, ${theme.bg}d9 100%)`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(circle at 20% 28%, ${theme.glow}, transparent 34%), linear-gradient(90deg, rgba(2,6,23,0.34) 0%, transparent 48%)`,
          mixBlendMode: 'screen',
          opacity: 0.72,
        }}
      />
    </>
  );
}

function FrameShell({
  children,
  theme,
  payload,
  scene,
}: {
  children: ReactNode;
  theme: Theme;
  payload: RemotionPromptPayload;
  scene: VideoPlanScene;
}) {
  const frame = useCurrentFrame();
  const metrics = useCanvasMetrics();
  const sceneAsset = pickSceneAsset(scene, payload.visualAssets);
  return (
    <div
      style={{
        width: metrics.width,
        height: metrics.height,
        position: 'relative',
        padding: `${metrics.paddingTop}px ${metrics.paddingX}px ${metrics.paddingBottom}px`,
        overflow: 'hidden',
      }}
    >
      <SceneBackdrop asset={sceneAsset} theme={theme} frame={frame} isVertical={metrics.isVertical} />
      <div
        style={{
          position: 'absolute',
          top: metrics.isVertical ? 42 : 38,
          left: metrics.isVertical ? 42 : 50,
        }}
      >
        <CategoryBadge category={payload.category} theme={theme} />
      </div>
      {children}
      <SourceLine value={scene.source_line} theme={theme} />
    </div>
  );
}

function PlannerTag({ label, theme, strong = false }: { label: string; theme: Theme; strong?: boolean }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: strong ? '10px 16px' : '8px 14px',
        borderRadius: 999,
        background: strong ? theme.panelStrong : `${theme.accent}1f`,
        border: `1px solid ${theme.line}`,
        color: theme.ink,
        fontSize: strong ? 15 : 13,
        fontWeight: 800,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}
    >
      {label}
    </span>
  );
}

type VerticalVariant = 'generic' | 'scoreboard' | 'timeline' | 'document' | 'memorial' | 'reaction';

function resolveVerticalVariant(layoutFamily?: LayoutFamily | null): VerticalVariant {
  switch (layoutFamily) {
    case 'scoreboard_stack':
    case 'price_impact_stack':
      return 'scoreboard';
    case 'map_casualty_stack':
    case 'rescue_sequence_stack':
    case 'timeline_stack':
      return 'timeline';
    case 'document_context_stack':
    case 'quote_context_stack':
    case 'panel_listing_stack':
      return 'document';
    case 'memorial_profile_stack':
      return 'memorial';
    case 'reaction_split_stack':
      return 'reaction';
    default:
      return 'generic';
  }
}

function renderVerticalDetailPanel(args: {
  variant: VerticalVariant;
  points: string[];
  scene: VideoPlanScene;
  theme: Theme;
  sourceAttribution: string;
  factNotes: string[];
}) {
  const { variant, points, scene, theme, sourceAttribution, factNotes } = args;

  if (variant === 'timeline') {
    const timelineItems = clamp(points.length ? points : factNotes, 4);
    return (
      <div
        style={{
          minHeight: '34%',
          borderRadius: 32,
          background: theme.panel,
          border: `1px solid ${theme.line}`,
          padding: '24px 24px 28px',
          display: 'grid',
          gap: 16,
          alignContent: 'start',
        }}
      >
        {timelineItems.map((item, index) => (
          <div
            key={`${item}-${index}`}
            style={{
              display: 'grid',
              gridTemplateColumns: '28px 1fr',
              gap: 16,
              alignItems: 'start',
              position: 'relative',
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 999,
                background: `${theme.accent}24`,
                border: `1px solid ${theme.line}`,
                display: 'grid',
                placeItems: 'center',
                color: theme.ink,
                fontSize: 12,
                fontWeight: 800,
              }}
            >
              {index + 1}
            </div>
            <div style={{ color: theme.ink, fontSize: item.length > 110 ? 24 : 28, lineHeight: 1.34, fontWeight: 650 }}>
              {item}
            </div>
          </div>
        ))}
        {sourceAttribution ? (
          <div style={{ marginTop: 6, color: theme.softInk, fontSize: 15, lineHeight: 1.45 }}>{sourceAttribution}</div>
        ) : null}
      </div>
    );
  }

  if (variant === 'document') {
    return (
      <div
        style={{
          minHeight: '32%',
          borderRadius: 32,
          background: theme.panel,
          border: `1px solid ${theme.line}`,
          padding: '24px 24px 28px',
          display: 'grid',
          gap: 18,
        }}
      >
        <div
          style={{
            borderRadius: 24,
            padding: '20px 20px 22px',
            background: `${theme.accent}14`,
            border: `1px solid ${theme.line}`,
          }}
        >
          <div style={{ color: theme.softInk, fontSize: 13, fontWeight: 800, letterSpacing: '0.16em', textTransform: 'uppercase' }}>
            Context
          </div>
          <div style={{ marginTop: 12, color: theme.ink, fontSize: scene.body.length > 150 ? 25 : 30, lineHeight: 1.34, fontWeight: 700 }}>
            {scene.body || scene.headline}
          </div>
        </div>
        {points.length > 0 ? (
          <div style={{ display: 'grid', gap: 12 }}>
            {clamp(points, 2).map((point, index) => (
              <div
                key={`${point}-${index}`}
                style={{
                  borderRadius: 20,
                  border: `1px solid ${theme.line}`,
                  padding: '16px 18px',
                  color: theme.ink,
                  fontSize: point.length > 90 ? 22 : 25,
                  lineHeight: 1.34,
                  background: 'rgba(15,23,42,0.18)',
                }}
              >
                {point}
              </div>
            ))}
          </div>
        ) : null}
        {sourceAttribution ? (
          <div style={{ color: theme.softInk, fontSize: 14, lineHeight: 1.42 }}>{sourceAttribution}</div>
        ) : null}
      </div>
    );
  }

  if (variant === 'memorial') {
    return (
      <div
        style={{
          minHeight: '30%',
          borderRadius: 32,
          background: theme.panel,
          border: `1px solid ${theme.line}`,
          padding: '24px 24px 28px',
          display: 'grid',
          gap: 16,
        }}
      >
        <div style={{ color: theme.softInk, fontSize: 14, fontWeight: 800, letterSpacing: '0.18em', textTransform: 'uppercase' }}>
          Legacy
        </div>
        <div style={{ color: theme.ink, fontSize: 30, lineHeight: 1.34, fontWeight: 650 }}>
          {scene.body || factNotes[0] || scene.headline}
        </div>
        {factNotes.length > 0 ? (
          <div style={{ display: 'grid', gap: 12 }}>
            {clamp(factNotes, 2).map((item, index) => (
              <div key={`${item}-${index}`} style={{ color: theme.softInk, fontSize: 21, lineHeight: 1.4 }}>
                {item}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  if (variant === 'reaction') {
    const reactionPoints = clamp(points.length ? points : factNotes, 2);
    return (
      <div
        style={{
          minHeight: '32%',
          borderRadius: 32,
          background: theme.panel,
          border: `1px solid ${theme.line}`,
          padding: '22px 22px 26px',
          display: 'grid',
          gap: 14,
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: reactionPoints.length > 1 ? '1fr 1fr' : '1fr', gap: 14 }}>
          {reactionPoints.map((item, index) => (
            <div
              key={`${item}-${index}`}
              style={{
                borderRadius: 24,
                padding: '18px 18px 20px',
                background: theme.panelStrong,
                border: `1px solid ${theme.line}`,
              }}
            >
              <div style={{ color: theme.softInk, fontSize: 12, fontWeight: 800, letterSpacing: '0.16em', textTransform: 'uppercase' }}>
                {index === 0 ? 'Signal' : 'Reaction'}
              </div>
              <div style={{ marginTop: 12, color: theme.ink, fontSize: item.length > 90 ? 21 : 24, lineHeight: 1.35, fontWeight: 700 }}>
                {item}
              </div>
            </div>
          ))}
        </div>
        {sourceAttribution ? (
          <div style={{ color: theme.softInk, fontSize: 14, lineHeight: 1.42 }}>{sourceAttribution}</div>
        ) : null}
      </div>
    );
  }

  if (variant === 'scoreboard') {
    return (
      <div
        style={{
          minHeight: '32%',
          borderRadius: 32,
          background: theme.panel,
          border: `1px solid ${theme.line}`,
          padding: '22px 22px 26px',
          display: 'grid',
          gap: 14,
        }}
      >
        {scene.key_data ? (
          <div
            style={{
              borderRadius: 24,
              padding: '18px 20px',
              background: theme.panelStrong,
              border: `1px solid ${theme.line}`,
              color: theme.ink,
              fontSize: scene.key_data.length > 30 ? 28 : 34,
              lineHeight: 1.1,
              fontWeight: 900,
            }}
          >
            {scene.key_data}
          </div>
        ) : null}
        {(points.length > 0 ? points : factNotes).slice(0, 3).map((point, index) => (
          <div
            key={`${point}-${index}`}
            style={{
              display: 'grid',
              gridTemplateColumns: '26px 1fr',
              gap: 14,
              alignItems: 'start',
              color: theme.ink,
            }}
          >
            <div
              style={{
                width: 26,
                height: 26,
                borderRadius: 999,
                background: `${theme.accent}24`,
                border: `1px solid ${theme.line}`,
                display: 'grid',
                placeItems: 'center',
                fontSize: 12,
                fontWeight: 800,
              }}
            >
              {index + 1}
            </div>
            <div style={{ fontSize: point.length > 95 ? 22 : 26, lineHeight: 1.34, fontWeight: 650 }}>{point}</div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: '34%',
        borderRadius: 32,
        background: theme.panel,
        border: `1px solid ${theme.line}`,
        padding: '24px 24px 28px',
        display: 'grid',
        gap: 16,
        alignContent: 'start',
      }}
    >
      {points.length > 0 ? (
        points.map((point, index) => (
          <div
            key={`${point}-${index}`}
            style={{
              display: 'grid',
              gridTemplateColumns: '32px 1fr',
              gap: 14,
              alignItems: 'start',
            }}
          >
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 999,
                background: `${theme.accent}24`,
                border: `1px solid ${theme.line}`,
                display: 'grid',
                placeItems: 'center',
                color: theme.ink,
                fontSize: 14,
                fontWeight: 800,
              }}
            >
              {index + 1}
            </div>
            <div
              style={{
                color: theme.ink,
                fontSize: point.length > 110 ? 24 : 28,
                lineHeight: 1.35,
                fontWeight: 650,
              }}
            >
              {point}
            </div>
          </div>
        ))
      ) : (
        <div
          style={{
            color: theme.softInk,
            fontSize: 26,
            lineHeight: 1.4,
          }}
        >
          {scene.body || scene.headline}
        </div>
      )}
    </div>
  );
}

function VerticalLayout({
  scene,
  theme,
  payload,
  sceneIndex,
}: {
  scene: VideoPlanScene;
  theme: Theme;
  payload: RemotionPromptPayload;
  sceneIndex: number;
}) {
  const hero = useReveal(0);
  const details = useReveal(8);
  const extras = useReveal(14);
  const planningDecision = payload.planningDecision;
  const storyFactPack = payload.storyFactPack;
  const sceneBlueprint = payload.outputBlueprint?.vertical_video?.scene_blueprints?.[sceneIndex] ?? null;
  const variant = resolveVerticalVariant(planningDecision?.layout_family);
  const points = clamp(
    uniqueText([
      ...scene.supporting_points,
      scene.body,
      storyFactPack?.what_changed,
      sceneIndex > 0 ? storyFactPack?.why_now : null,
    ]),
    variant === 'reaction' ? 2 : 3
  );
  const chips = clamp(uniqueText([...scene.key_figures, ...(storyFactPack?.key_numbers ?? [])]), 4);
  const sourceAttribution = storyFactPack?.source_attribution || scene.source_line;
  const metaTags = clamp(
    uniqueText([
      planningDecision?.status ? formatPlannerLabel(planningDecision.status) : null,
      planningDecision?.story_family ? formatPlannerLabel(planningDecision.story_family) : null,
      sceneBlueprint?.goal ? formatPlannerLabel(sceneBlueprint.goal) : null,
      sceneBlueprint?.safe_voice_rule ? formatPlannerLabel(sceneBlueprint.safe_voice_rule) : null,
      ...(planningDecision?.risk_flags ?? []).slice(0, 1).map((flag) => formatPlannerLabel(flag)),
    ]),
    4
  );
  const factNotes = clamp(
    uniqueText([
      ...(storyFactPack?.key_entities ?? []),
      ...(storyFactPack?.key_locations ?? []),
      storyFactPack?.why_now,
    ]),
    3
  );
  const panelLabel = sceneBlueprint?.visual_type
    ? formatPlannerLabel(sceneBlueprint.visual_type)
    : planningDecision?.layout_family
      ? formatPlannerLabel(planningDecision.layout_family)
      : formatPlannerLabel(scene.purpose);

  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      <div
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-end',
          gap: 24,
        }}
      >
        <div
          style={{
            borderRadius: 36,
            background: 'linear-gradient(180deg, rgba(15,23,42,0.78) 0%, rgba(15,23,42,0.58) 100%)',
            border: `1px solid ${theme.line}`,
            boxShadow: `0 24px 80px ${theme.glow}`,
            backdropFilter: 'blur(18px)',
            padding: '30px 28px',
            opacity: hero.opacity,
            transform: `translateY(${hero.translateY}px)`,
          }}
        >
          <h1
            style={{
              margin: 0,
              color: theme.ink,
              fontSize: scene.headline.length > 90 ? 56 : scene.headline.length > 58 ? 64 : 78,
              lineHeight: 0.96,
              fontWeight: 900,
              letterSpacing: '-0.07em',
            }}
          >
            {scene.headline}
          </h1>
          {scene.body ? (
            <p
              style={{
                margin: '22px 0 0',
                color: theme.softInk,
                fontSize: scene.body.length > 180 ? 28 : 32,
                lineHeight: 1.34,
                maxWidth: '100%',
              }}
            >
              {scene.body}
            </p>
          ) : null}
        </div>

        {(scene.key_data || chips.length > 0 || metaTags.length > 0) ? (
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 12,
              opacity: extras.opacity,
              transform: `translateY(${extras.translateY}px)`,
            }}
          >
            {metaTags.map((item, index) => (
              <PlannerTag key={`${item}-${index}`} label={item} theme={theme} strong={index === 0} />
            ))}
            {scene.key_data ? (
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '16px 20px',
                  borderRadius: 24,
                  background: theme.panelStrong,
                  border: `1px solid ${theme.line}`,
                  color: theme.ink,
                  fontSize: scene.key_data.length > 32 ? 24 : 28,
                  fontWeight: 800,
                  lineHeight: 1.1,
                  boxShadow: `0 0 32px ${theme.glow}`,
                }}
              >
                {scene.key_data}
              </div>
            ) : null}
            {chips.map((item) => (
              <Chip key={item} label={item} theme={theme} />
            ))}
          </div>
        ) : null}

        <div
          style={{
            opacity: details.opacity,
            transform: `translateY(${details.translateY}px)`,
          }}
        >
          <div
            style={{
              marginBottom: 12,
              color: theme.softInk,
              fontSize: 14,
              fontWeight: 800,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
            }}
          >
            {panelLabel}
          </div>
          {renderVerticalDetailPanel({
            variant,
            points,
            scene,
            theme,
            sourceAttribution,
            factNotes,
          })}
        </div>
      </div>
    </FrameShell>
  );
}

function HeadlineLayout({ scene, theme, payload }: { scene: VideoPlanScene; theme: Theme; payload: RemotionPromptPayload }) {
  const title = useReveal(0);
  const body = useReveal(8);
  const chips = useReveal(14);

  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      <div
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 24,
        }}
      >
        <h1
          style={{
            margin: 0,
            maxWidth: 980,
            textAlign: 'center',
            color: theme.ink,
            fontSize: scene.headline.length > 58 ? 50 : 64,
            lineHeight: 1.04,
            fontWeight: 850,
            letterSpacing: '-0.05em',
            opacity: title.opacity,
            transform: `translateY(${title.translateY}px)`,
          }}
        >
          {scene.headline}
        </h1>
        {scene.body ? (
          <p
            style={{
              margin: 0,
              maxWidth: 820,
              textAlign: 'center',
              color: theme.softInk,
            fontSize: scene.body.length > 180 ? 20 : 24,
              lineHeight: 1.45,
              opacity: body.opacity,
              transform: `translateY(${body.translateY}px)`,
            }}
          >
          {scene.body}
          </p>
        ) : null}
        {scene.key_figures.length > 0 ? (
          <div
            style={{
              display: 'flex',
              gap: 12,
              flexWrap: 'wrap',
              justifyContent: 'center',
              opacity: chips.opacity,
              transform: `translateY(${chips.translateY}px)`,
            }}
          >
            {clamp(scene.key_figures, 4).map((item) => (
              <Chip key={item} label={item} theme={theme} />
            ))}
          </div>
        ) : null}
      </div>
    </FrameShell>
  );
}

function FullBleedLayout({ scene, theme, payload }: { scene: VideoPlanScene; theme: Theme; payload: RemotionPromptPayload }) {
  const hero = useReveal(0);
  const copy = useReveal(10);
  const hasAsset = scene.asset_ids.length > 0 || payload.visualAssets.length > 0;
  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      {!hasAsset ? (
        <div
          style={{
            position: 'absolute',
            inset: 80,
            borderRadius: 42,
            background: `linear-gradient(160deg, ${theme.panelStrong} 0%, rgba(2,6,23,0.24) 100%)`,
            border: `1px solid ${theme.line}`,
            boxShadow: `0 0 80px ${theme.glow}`,
          }}
        />
      ) : null}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 24,
          padding: hasAsset ? '58px 36px 124px' : '60px',
        }}
      >
        {hasAsset ? (
          <div
            style={{
              position: 'absolute',
              left: 12,
              top: 86,
              bottom: 96,
              width: 760,
              borderRadius: 36,
              background: 'linear-gradient(180deg, rgba(2,6,23,0.62) 0%, rgba(2,6,23,0.34) 100%)',
              border: `1px solid ${theme.line}`,
              boxShadow: `0 0 60px ${theme.glow}`,
              backdropFilter: 'blur(14px)',
            }}
          />
        ) : null}
        <h1
          style={{
            margin: 0,
            maxWidth: hasAsset ? 700 : 900,
            color: theme.ink,
            fontSize: scene.headline.length > 58 ? 54 : 68,
            lineHeight: 1,
            fontWeight: 900,
            letterSpacing: '-0.06em',
            opacity: hero.opacity,
            transform: `translateY(${hero.translateY}px)`,
            textShadow: hasAsset ? '0 10px 40px rgba(2,6,23,0.55)' : `0 0 40px ${theme.glow}`,
          }}
        >
          {scene.headline}
        </h1>
        {scene.body ? (
          <p
            style={{
              margin: 0,
              maxWidth: hasAsset ? 660 : 760,
              color: theme.softInk,
              fontSize: scene.body.length > 180 ? 21 : 25,
              lineHeight: 1.42,
              opacity: copy.opacity,
              transform: `translateY(${copy.translateY}px)`,
            }}
          >
            {scene.body}
          </p>
        ) : null}
      </div>
    </FrameShell>
  );
}

function SplitLayout({ scene, theme, payload }: { scene: VideoPlanScene; theme: Theme; payload: RemotionPromptPayload }) {
  const left = useReveal(0);
  const right = useReveal(10);
  const points = clamp(scene.supporting_points.length ? scene.supporting_points : [scene.body].filter(Boolean), 4);
  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      <div
        style={{
          height: '100%',
          display: 'grid',
          gridTemplateColumns: '1.05fr 0.95fr',
          gap: 28,
          alignItems: 'center',
        }}
      >
        <div style={{ opacity: left.opacity, transform: `translateX(${-left.translateX}px)` }}>
          <h2
            style={{
              margin: 0,
              color: theme.ink,
              fontSize: 52,
              lineHeight: 1.04,
              fontWeight: 800,
              letterSpacing: '-0.05em',
            }}
          >
            {scene.headline}
          </h2>
          {scene.body ? (
            <p
              style={{
                margin: '18px 0 0',
                color: theme.softInk,
                fontSize: scene.body.length > 180 ? 19 : 22,
                lineHeight: 1.45,
                maxWidth: 620,
              }}
            >
              {scene.body}
            </p>
          ) : null}
        </div>
        <div
          style={{
            display: 'grid',
            gap: 14,
            opacity: right.opacity,
            transform: `translateX(${right.translateX}px)`,
          }}
        >
          {points.map((point, index) => (
            <div
              key={`${point}-${index}`}
              style={{
                borderRadius: 24,
                background: theme.panelStrong,
                border: `1px solid ${theme.line}`,
                padding: '18px 20px',
                color: theme.ink,
              }}
            >
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 800,
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  color: theme.softInk,
                }}
              >
                Point {index + 1}
              </div>
              <div style={{ marginTop: 10, fontSize: point.length > 80 ? 17 : 20, lineHeight: 1.42 }}>{point}</div>
            </div>
          ))}
          {scene.key_figures.length > 0 ? (
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', paddingTop: 4 }}>
              {clamp(scene.key_figures, 4).map((item) => (
                <Chip key={item} label={item} theme={theme} />
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </FrameShell>
  );
}

function StatLayout({ scene, theme, payload }: { scene: VideoPlanScene; theme: Theme; payload: RemotionPromptPayload }) {
  const headline = useReveal(0);
  const stat = useReveal(8);
  const copy = useReveal(14);
  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      <div
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          gap: 20,
          textAlign: 'center',
        }}
      >
        <div style={{ opacity: headline.opacity, transform: `translateY(${headline.translateY}px)` }}>
          <h2
            style={{
              margin: 0,
              color: theme.ink,
              fontSize: 40,
              lineHeight: 1.15,
              fontWeight: 800,
              letterSpacing: '-0.04em',
              maxWidth: 780,
            }}
          >
            {scene.headline}
          </h2>
        </div>
        {scene.key_data ? (
          <div
            style={{
              padding: '28px 36px',
              borderRadius: 36,
              background: theme.panelStrong,
              border: `1px solid ${theme.line}`,
              boxShadow: `0 0 60px ${theme.glow}`,
              opacity: stat.opacity,
              transform: `scale(${stat.scale})`,
            }}
          >
            <div
              style={{
                color: theme.ink,
                fontSize: scene.key_data.length > 28 ? 44 : 62,
                lineHeight: 1.04,
                fontWeight: 900,
                letterSpacing: '-0.05em',
              }}
            >
              {scene.key_data}
            </div>
          </div>
        ) : null}
        {scene.body ? (
          <p
            style={{
              margin: 0,
              maxWidth: 760,
              color: theme.softInk,
              fontSize: scene.body.length > 180 ? 19 : 22,
              lineHeight: 1.45,
              opacity: copy.opacity,
              transform: `translateY(${copy.translateY}px)`,
            }}
          >
            {scene.body}
          </p>
        ) : null}
      </div>
    </FrameShell>
  );
}

function TimelineLayout({ scene, theme, payload }: { scene: VideoPlanScene; theme: Theme; payload: RemotionPromptPayload }) {
  const reveal = useReveal(0);
  const points = clamp(scene.supporting_points.length ? scene.supporting_points : [scene.body].filter(Boolean), 4);
  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      <div
        style={{
          height: '100%',
          display: 'grid',
          gridTemplateColumns: '0.95fr 1.05fr',
          gap: 28,
          alignItems: 'center',
        }}
      >
        <div style={{ opacity: reveal.opacity, transform: `translateX(${-reveal.translateX}px)` }}>
          <h2
            style={{
              margin: 0,
              color: theme.ink,
              fontSize: 48,
              lineHeight: 1.06,
              fontWeight: 850,
              letterSpacing: '-0.05em',
            }}
          >
            {scene.headline}
          </h2>
          {scene.body ? (
            <p
              style={{
                margin: '18px 0 0',
                color: theme.softInk,
                fontSize: scene.body.length > 180 ? 18 : 21,
                lineHeight: 1.45,
                maxWidth: 540,
              }}
            >
              {scene.body}
            </p>
          ) : null}
        </div>
        <div style={{ display: 'grid', gap: 14 }}>
          {points.map((point, index) => (
            <div
              key={`${point}-${index}`}
              style={{
                display: 'grid',
                gridTemplateColumns: '44px 1fr',
                gap: 16,
                alignItems: 'start',
                padding: '14px 0',
                borderBottom: index < points.length - 1 ? `1px solid ${theme.line}` : 'none',
              }}
            >
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 999,
                  background: `${theme.accent}24`,
                  border: `1px solid ${theme.line}`,
                  display: 'grid',
                  placeItems: 'center',
                  color: theme.ink,
                  fontWeight: 800,
                }}
              >
                {index + 1}
              </div>
              <div style={{ color: theme.ink, fontSize: point.length > 80 ? 17 : 20, lineHeight: 1.42 }}>{point}</div>
            </div>
          ))}
        </div>
      </div>
    </FrameShell>
  );
}

function QuoteLayout({ scene, theme, payload }: { scene: VideoPlanScene; theme: Theme; payload: RemotionPromptPayload }) {
  const reveal = useReveal(0);
  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      <div
        style={{
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            maxWidth: 980,
            textAlign: 'center',
            opacity: reveal.opacity,
            transform: `translateY(${reveal.translateY}px)`,
          }}
        >
          <div style={{ color: theme.accent, fontSize: 88, lineHeight: 0.8, fontWeight: 700 }}>“</div>
          <h2
            style={{
              margin: '0 auto',
              color: theme.ink,
              fontSize: 50,
              lineHeight: 1.14,
              fontWeight: 800,
              letterSpacing: '-0.04em',
            }}
          >
            {scene.headline}
          </h2>
          {scene.body ? (
            <p
              style={{
                margin: '22px auto 0',
                color: theme.softInk,
                fontSize: scene.body.length > 180 ? 19 : 22,
                lineHeight: 1.45,
                maxWidth: 760,
              }}
            >
              {scene.body}
            </p>
          ) : null}
        </div>
      </div>
    </FrameShell>
  );
}

function ComparisonLayout({ scene, theme, payload }: { scene: VideoPlanScene; theme: Theme; payload: RemotionPromptPayload }) {
  const reveal = useReveal(0);
  const cards = clamp(scene.supporting_points.length ? scene.supporting_points : scene.key_figures, 2);
  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      <div
        style={{
          height: '100%',
          display: 'grid',
          gridTemplateRows: 'auto 1fr',
          gap: 24,
        }}
      >
        <div style={{ opacity: reveal.opacity, transform: `translateY(${reveal.translateY}px)` }}>
          <h2
            style={{
              margin: '80px 0 0',
              textAlign: 'center',
              color: theme.ink,
              fontSize: 48,
              lineHeight: 1.06,
              fontWeight: 850,
              letterSpacing: '-0.05em',
            }}
          >
            {scene.headline}
          </h2>
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: cards.length >= 2 ? '1fr 1fr' : '1fr',
            gap: 22,
            alignItems: 'stretch',
          }}
        >
          {cards.map((item, index) => (
            <div
              key={`${item}-${index}`}
              style={{
                borderRadius: 32,
                background: theme.panelStrong,
                border: `1px solid ${theme.line}`,
                padding: '28px 26px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                boxShadow: `0 0 30px ${theme.glow}`,
              }}
            >
              <div
                style={{
                  color: theme.softInk,
                  fontSize: 12,
                  fontWeight: 800,
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                }}
              >
                {index === 0 ? 'Side A' : 'Side B'}
              </div>
              <div
                style={{
                  marginTop: 14,
                  color: theme.ink,
                  fontSize: item.length > 80 ? 22 : 28,
                  lineHeight: 1.25,
                  fontWeight: 700,
                }}
              >
                {item}
              </div>
            </div>
          ))}
        </div>
      </div>
    </FrameShell>
  );
}

function MinimalLayout({ scene, theme, payload }: { scene: VideoPlanScene; theme: Theme; payload: RemotionPromptPayload }) {
  const reveal = useReveal(0);
  return (
    <FrameShell theme={theme} payload={payload} scene={scene}>
      <div
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          gap: 16,
        }}
      >
        <h2
          style={{
            margin: 0,
            maxWidth: 860,
            textAlign: 'center',
            color: theme.ink,
            fontSize: scene.headline.length > 70 ? 38 : 48,
            lineHeight: 1.14,
            fontWeight: 800,
            letterSpacing: '-0.04em',
            opacity: reveal.opacity,
            transform: `translateY(${reveal.translateY}px)`,
          }}
        >
          {scene.headline}
        </h2>
        {scene.body ? (
          <p
            style={{
              margin: 0,
              maxWidth: 700,
              textAlign: 'center',
              color: theme.softInk,
                fontSize: scene.body.length > 150 ? 18 : 20,
              lineHeight: 1.45,
              opacity: reveal.opacity,
            }}
          >
              {scene.body}
          </p>
        ) : null}
      </div>
    </FrameShell>
  );
}

function renderSceneByLayout(
  layout: VideoPlanLayoutHint,
  scene: VideoPlanScene,
  payload: RemotionPromptPayload,
  theme: Theme,
  sceneIndex: number
) {
  if (payload.videoPlan.master_format === '9:16') {
    return <VerticalLayout scene={scene} theme={theme} payload={payload} sceneIndex={sceneIndex} />;
  }

  switch (layout) {
    case 'full-bleed':
      return <FullBleedLayout scene={scene} theme={theme} payload={payload} />;
    case 'split':
      return <SplitLayout scene={scene} theme={theme} payload={payload} />;
    case 'stat':
      return <StatLayout scene={scene} theme={theme} payload={payload} />;
    case 'timeline':
      return <TimelineLayout scene={scene} theme={theme} payload={payload} />;
    case 'quote':
      return <QuoteLayout scene={scene} theme={theme} payload={payload} />;
    case 'comparison':
      return <ComparisonLayout scene={scene} theme={theme} payload={payload} />;
    case 'minimal':
      return <MinimalLayout scene={scene} theme={theme} payload={payload} />;
    case 'headline':
    default:
      return <HeadlineLayout scene={scene} theme={theme} payload={payload} />;
  }
}

function VideoPlanSceneView({
  scene,
  payload,
  theme,
  durationInFrames,
  sceneIndex,
}: {
  scene: VideoPlanScene;
  payload: RemotionPromptPayload;
  theme: Theme;
  durationInFrames: number;
  sceneIndex: number;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const reveal = spring({
    fps,
    frame,
    config: { damping: 16, stiffness: 120 },
  });
  const opacity = interpolate(frame, [0, 8, durationInFrames - 10, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const translateY = interpolate(reveal, [0, 1], [26, 0]);
  const scale = interpolate(reveal, [0, 1], [0.975, 1]);

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${translateY}px) scale(${scale})`,
      }}
    >
      {renderSceneByLayout(scene.layout_hint, scene, payload, theme, sceneIndex)}
    </div>
  );
}

export function PromptVideo({ payload }: { payload: RemotionPromptPayload }) {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const theme = categoryThemes[payload.category] ?? categoryThemes.general;
  const scenes = payload.videoPlan.scenes.length ? payload.videoPlan.scenes : [];
  const containerOpacity = interpolate(frame, [0, 14, durationInFrames - 16, durationInFrames], [0, 1, 1, 0]);

  let cursor = 0;

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        fontFamily: '"Avenir Next", "SF Pro Text", "Segoe UI", sans-serif',
        color: theme.ink,
        opacity: containerOpacity,
        overflow: 'hidden',
      }}
    >
      <BackgroundMotif theme={theme} frame={frame} />

      {scenes.map((scene, index) => {
        const from = cursor;
        const remaining = durationInFrames - cursor;
        const sceneFrames = Math.max(1, Math.round(scene.duration_seconds * fps));
        const duration = index === scenes.length - 1 ? remaining : Math.min(sceneFrames, remaining);
        cursor += duration;

        return (
          <Sequence key={scene.scene_id || `${scene.purpose}-${index}`} from={from} durationInFrames={duration}>
            <VideoPlanSceneView
              scene={scene}
              payload={payload}
              theme={theme}
              durationInFrames={duration}
              sceneIndex={index}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
}
