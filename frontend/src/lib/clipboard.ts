import type { Segment } from "../types";

// #18: format caption yang di-copy — SUMBER TUNGGAL, dipakai SegmentCard
// & JobDetail (sebelumnya di-duplikat di 2 file).
export function formatCopyText(seg: Segment): string {
  return seg.affiliate_caption
    ? seg.hashtags && seg.hashtags.length > 0
      ? `${seg.affiliate_caption}\n\n${seg.hashtags.join(" ")}`
      : seg.affiliate_caption
    : seg.caption_text || "";
}
