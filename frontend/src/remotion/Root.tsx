import { Composition } from 'remotion';
import { PromptVideo } from './PromptVideo';
import type { RemotionPromptPayload } from '../types/analysis';

// Minimal valid payload used only for composition registration.
// Real data is injected via inputProps at render time.
const defaultPayload = {
  headline: 'News Video',
  summary: 'News summary',
  durationSeconds: 45,
  category: 'general',
  keyPoints: [],
  whyItMatters: '',
  sources: [],
  promptText: '',
  formatHint: '',
  storyAngle: '',
  visualBrief: '',
  motionTreatment: '',
  transitionStyle: '',
  tone: '',
  sceneSequence: [],
  designKeywords: [],
  mustInclude: [],
  avoid: [],
  visualAssets: [],
  videoContent: null,
  storyboard: null,
  videoPlan: {
    title: 'News Video',
    master_format: '9:16',
    duration_seconds: 45,
    pacing_hint: 'normal',
    audience_mode: 'sound_off_first',
    source_visibility: 'none',
    scenes: [],
  },
} as unknown as RemotionPromptPayload;

export function Root() {
  return (
    <>
      <Composition
        id="PromptVideo"
        component={PromptVideo}
        durationInFrames={1350}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ payload: defaultPayload, audioUrl: undefined }}
        calculateMetadata={({ props }) => {
          const fps = 30;
          const durationInFrames = Math.max(
            fps * 8,
            Math.round(props.payload.durationSeconds * fps),
          );
          const isVertical = props.payload.videoPlan?.master_format === '9:16';
          return {
            durationInFrames,
            width: isVertical ? 1080 : 1280,
            height: isVertical ? 1920 : 720,
          };
        }}
      />
    </>
  );
}
