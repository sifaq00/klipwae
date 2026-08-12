import type { CaptionStyle, Job, Segment } from "../types";

const BASE = "/api";

async function handle(res: Response): Promise<any> {
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* keep statusText */
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function listJobs(): Promise<Job[]> {
  return handle(await fetch(`${BASE}/jobs`));
}

export async function getSettings(): Promise<{ video_download_resolution?: number }> {
  return handle(await fetch(`${BASE}/settings`));
}

export async function getJob(id: string): Promise<Job> {
  return handle(await fetch(`${BASE}/jobs/${id}`));
}

export async function createJob(url: string): Promise<{ job_id: string }> {
  return handle(
    await fetch(`${BASE}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    })
  );
}

export async function killJob(id: string): Promise<void> {
  await handle(await fetch(`${BASE}/jobs/${id}/kill`, { method: "POST" }));
}

export async function retryJob(id: string): Promise<void> {
  await handle(await fetch(`${BASE}/jobs/${id}/retry`, { method: "POST" }));
}

export async function getSegments(id: string): Promise<Segment[]> {
  return handle(await fetch(`${BASE}/jobs/${id}/segments`));
}

export async function markSegment(id: number, field: "reviewed" | "posted"): Promise<void> {
  await handle(await fetch(`${BASE}/segments/${id}/${field}`, { method: "POST" }));
}

export async function rejectSegment(id: number): Promise<void> {
  await handle(await fetch(`${BASE}/segments/${id}/reject`, { method: "POST" }));
}

export async function deleteJob(id: string): Promise<void> {
  await handle(await fetch(`${BASE}/jobs/${id}`, { method: "DELETE" }));
}

export function streamLog(
  id: string,
  onLog: (line: string) => void,
  onDone: () => void,
  since = 0
): EventSource {
  const es = new EventSource(`${BASE}/jobs/${id}/log?since=${since}`);
  es.addEventListener("log", (e) => onLog(e.data));
  es.addEventListener("done", () => {
    es.close();
    onDone();
  });
  es.onerror = () => es.close();
  return es;
}

export async function listFonts(): Promise<string[]> {
  const res = await fetch(`${BASE}/fonts`);
  return (await handle(res)).fonts;
}

export async function getCaptionStyle(): Promise<CaptionStyle> {
  return handle(await fetch(`${BASE}/caption-style`));
}

export async function saveCaptionStyle(style: CaptionStyle): Promise<void> {
  await handle(
    await fetch(`${BASE}/caption-style`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(style),
    })
  );
}

export async function getJobCaptionStyle(id: string): Promise<CaptionStyle> {
  return handle(await fetch(`${BASE}/jobs/${id}/caption-style`));
}

export async function saveJobCaptionStyle(id: string, style: CaptionStyle): Promise<void> {
  await handle(
    await fetch(`${BASE}/jobs/${id}/caption-style`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(style),
    })
  );
}

export async function reburnCaptions(id: string): Promise<void> {
  await handle(await fetch(`${BASE}/jobs/${id}/reburn-captions`, { method: "POST" }));
}

export async function getStylePreview(style: CaptionStyle): Promise<string> {
  const res = await fetch(`${BASE}/caption-style/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(style),
  });
  return (await handle(res)).url;
}
