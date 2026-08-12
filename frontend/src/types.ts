export interface Job {
  id: string;
  url: string;
  title: string | null;
  channel: string | null;
  duration_sec: number | null;
  status: string;
  failed_stage: string | null;
  error_message: string | null;
  notice?: string | null;
  created_at: string;
  updated_at: string;
  running?: boolean;
  segment_count?: number;
  stages?: StageRun[];
}

export interface StageRun {
  id: number;
  job_id: string;
  stage: string;
  status: string;
  attempt: number;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

export interface Settings {
  whisper_model: string;
  whisper_device: string;
}

export interface Segment {
  id: number;
  job_id: string;
  clip_idx: number | null;
  start_time: string | null;
  end_time: string | null;
  product_mentioned: string | null;
  topic: string | null;
  confidence: number | null;
  reason: string | null;
  layout_type: string | null;
  clip_path: string | null;
  caption_path: string | null;
  caption_text: string | null;
  preview_url: string | null;
  thumb_url: string | null;
  caption_url: string | null;
  reviewed: number;
  posted: number;
}

export interface CaptionStyle {
  enabled: boolean;
  font: string;
  size: number;
  bold: boolean;
  italic: boolean;
  uppercase: boolean;
  pop: boolean;
  spacing: number;
  line_spacing: number;
  text_color: string;
  highlight_color: string;
  outline: number;
  outline_color: string;
  border_style: "outline" | "box";
  shadow: number;
  shadow_color: string;
  position: "bottom" | "top";
  margin_v: number;
  style: "highlight" | "static";
}
