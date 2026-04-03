import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type { ReactNode } from 'react';
import type { RemotionPromptPayload, VideoPlanLayoutHint, VideoPlanScene, VisualAsset } from '../types/analysis';

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

const categoryThemes: Record<string, Theme> = {
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

function truncateLabel(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, Math.max(0, limit - 3)).trimEnd()}...`;
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
}: {
  asset: VisualAsset | null;
  theme: Theme;
  frame: number;
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
            objectPosition: 'center 18%',
            transform: `translate3d(0, ${translateY}px, 0) scale(${scale})`,
            filter: 'brightness(0.62) saturate(1.02) contrast(1.04)',
          }}
        />
      </div>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `linear-gradient(180deg, rgba(2,6,23,0.1) 0%, rgba(2,6,23,0.22) 18%, rgba(2,6,23,0.48) 58%, ${theme.bg}d9 100%)`,
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
  const sceneAsset = pickSceneAsset(scene, payload.visualAssets);
  return (
    <div
      style={{
        width: 1280,
        height: 720,
        position: 'relative',
        padding: '48px 56px',
        overflow: 'hidden',
      }}
    >
      <SceneBackdrop asset={sceneAsset} theme={theme} frame={frame} />
      <div style={{ position: 'absolute', top: 38, left: 50 }}>
        <CategoryBadge category={payload.category} theme={theme} />
      </div>
      {children}
      <SourceLine value={scene.source_line} theme={theme} />
    </div>
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

function renderSceneByLayout(layout: VideoPlanLayoutHint, scene: VideoPlanScene, payload: RemotionPromptPayload, theme: Theme) {
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
}: {
  scene: VideoPlanScene;
  payload: RemotionPromptPayload;
  theme: Theme;
  durationInFrames: number;
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
      {renderSceneByLayout(scene.layout_hint, scene, payload, theme)}
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
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
}
