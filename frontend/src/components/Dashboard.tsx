import { useEffect, useRef, useState } from "react";
import type { Job, Segment } from "../types";
import { getSegments, killJob, markSegment, retryJob, streamLog } from "../lib/api";

interface Props {
  jobs: Job[];
  activeJob: string | null;
  onSetActive: (id: string | null) => void;
  onRefresh: () => void;
}

const STATUS_COLOR: Record<string, string> = {
  pending: "text-gray-400",
  running: "text-blue-400",
  downloading: "text-yellow-400",
  transcribing: "text-yellow-400",
  analyzing: "text-yellow-400",
  clipping: "text-yellow-400",
  captioning: "text-yellow-400",
  reframing: "text-yellow-400",
  done: "text-green-400",
  failed: "text-red-400",
  killed: "text-orange-400",
};

export function Dashboard({ jobs, activeJob, onSetActive, onRefresh }: Props) {
  const job = activeJob ? jobs.find((j) => j.id === activeJob) : null;
  const [logs, setLogs] = useState<string[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [previewId, setPreviewId] = useState<number | null>(null);
  const logEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!activeJob) return;
    setLogs([]);
    setSegments([]);
    setPreviewId(null);
    getSegments(activeJob).then(setSegments).catch(() => {});
    const es = streamLog(
      activeJob,
      (line) => setLogs((p) => [...p, line]),
      () => {
        getSegments(activeJob).then(setSegments).catch(() => {});
        onRefresh();
      }
    );
    return () => es.close();
  }, [activeJob, onRefresh]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleKill = async () => {
    if (!activeJob) return;
    try {
      await killJob(activeJob);
    } catch {
      // ignore
    }
    onRefresh();
  };

  const handleRetry = async () => {
    if (!activeJob) return;
    try {
      await retryJob(activeJob);
    } catch {
      // ignore
    }
    onRefresh();
  };

  const toggleSegment = async (seg: Segment, field: "reviewed" | "posted") => {
    await markSegment(seg.id, field);
    setSegments((prev) =>
      prev.map((s) =>
        s.id === seg.id ? { ...s, [field]: s[field] ? 0 : 1 } : s
      )
    );
  };

  const hasRunning = jobs.some((j) => j.running);
  const done = jobs.filter((j) => j.status === "done").length;
  const failed = jobs.filter((j) => j.status === "failed").length;

  return (
    <div className="space-y-4">
      {job ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <button
              className="text-xs text-gray-500 hover:text-gray-300"
              onClick={() => onSetActive(null)}
            >
              &larr; back
            </button>
            <div className="flex gap-2">
              {job.running && (
                <button
                  className="bg-red-700 hover:bg-red-600 rounded px-3 py-1 text-sm font-medium"
                  onClick={handleKill}
                >
                  KILL
                </button>
              )}
              {job.status !== "done" && !job.running && (
                <button
                  className="text-xs bg-blue-700 hover:bg-blue-600 rounded px-2 py-1"
                  onClick={handleRetry}
                >
                  retry
                </button>
              )}
            </div>
          </div>

          <div className="bg-gray-900 rounded p-3 space-y-1 text-xs font-mono">
            <div className="flex gap-4">
              <span className="text-gray-500">id</span>
              <span>{job.id}</span>
            </div>
            <div className="flex gap-4">
              <span className="text-gray-500">status</span>
              <span className={STATUS_COLOR[job.status] || ""}>
                {job.status}
              </span>
            </div>
            {job.title && (
              <div className="flex gap-4">
                <span className="text-gray-500">title</span>
                <span>{job.title}</span>
              </div>
            )}
            {job.stages && job.stages.length > 0 && (
              <div className="flex gap-4">
                <span className="text-gray-500">stages</span>
                <div className="flex gap-2 flex-wrap">
                  {job.stages.map((s) => (
                    <span
                      key={s.id}
                      className={
                        STATUS_COLOR[s.status] || "text-gray-400"
                      }
                    >
                      {s.stage}:{s.status}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {segments.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-gray-500">
                segments: <span className="text-gray-300">{segments.length}</span>
              </div>
              {segments.map((seg) => (
                <div key={seg.id} className="bg-gray-900 rounded p-3 space-y-2">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-mono text-gray-400">
                      {seg.start_time} - {seg.end_time}
                    </span>
                    <span className="text-gray-500">
                      conf {(seg.confidence ?? 0).toFixed(2)}
                    </span>
                    {seg.layout_type && (
                      <span className="text-gray-600">{seg.layout_type}</span>
                    )}
                    <span className="ml-auto flex gap-2">
                      <button
                        className={`rounded px-2 py-0.5 ${
                          seg.reviewed
                            ? "bg-green-700 hover:bg-green-600"
                            : "bg-gray-800 hover:bg-gray-700"
                        }`}
                        onClick={() => toggleSegment(seg, "reviewed")}
                      >
                        {seg.reviewed ? "reviewed" : "mark reviewed"}
                      </button>
                      <button
                        className={`rounded px-2 py-0.5 ${
                          seg.posted
                            ? "bg-green-700 hover:bg-green-600"
                            : "bg-gray-800 hover:bg-gray-700"
                        }`}
                        onClick={() => toggleSegment(seg, "posted")}
                      >
                        {seg.posted ? "posted" : "mark posted"}
                      </button>
                    </span>
                  </div>
                  {seg.topic && (
                    <div className="text-sm text-gray-300">{seg.topic}</div>
                  )}
                  {seg.product_mentioned && (
                    <div className="text-xs text-yellow-400">
                      product: {seg.product_mentioned}
                    </div>
                  )}
                  {seg.reason && (
                    <div className="text-xs text-gray-500">{seg.reason}</div>
                  )}
                  {seg.preview_url && (
                    <div className="space-y-2">
                      {previewId === seg.id ? (
                        <div className="space-y-1">
                          <video
                            controls
                            className="w-full max-h-72 bg-black rounded"
                            src={seg.preview_url}
                          />
                          {seg.caption_url && (
                            <a
                              className="text-xs text-blue-400 hover:underline"
                              href={seg.caption_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              .ass caption
                            </a>
                          )}
                          <button
                            className="text-xs text-gray-500 hover:text-gray-300"
                            onClick={() => setPreviewId(null)}
                          >
                            hide
                          </button>
                        </div>
                      ) : (
                        <button
                          className="text-xs bg-gray-800 hover:bg-gray-700 rounded px-2 py-0.5"
                          onClick={() => setPreviewId(seg.id)}
                        >
                          preview
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="bg-gray-900 rounded p-3 h-64 overflow-y-auto text-xs font-mono leading-relaxed">
            {logs.map((line, i) => (
              <div key={i} className="text-gray-300">
                {line}
              </div>
            ))}
            <div ref={logEnd} />
          </div>
        </div>
      ) : (
        <>
          <div className="flex gap-4 text-xs text-gray-500">
            <span>
              total: <span className="text-gray-300">{jobs.length}</span>
            </span>
            <span>
              done: <span className="text-green-400">{done}</span>
            </span>
            <span>
              failed: <span className="text-red-400">{failed}</span>
            </span>
            <span>
              running: <span className="text-blue-400">{hasRunning ? "yes" : "no"}</span>
            </span>
          </div>

          {jobs.length === 0 ? (
            <p className="text-gray-600 text-sm text-center py-8">
              No jobs yet. Paste a URL above.
            </p>
          ) : (
            <div className="space-y-1">
              {jobs.map((j) => (
                <div
                  key={j.id}
                  className="flex items-center gap-2 bg-gray-900 hover:bg-gray-800 rounded px-3 py-2"
                >
                  <button
                    className="flex-1 text-left flex items-center gap-3 text-sm"
                    onClick={() => onSetActive(j.id)}
                  >
                    <span
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        j.running
                          ? "bg-blue-400 animate-pulse"
                          : j.status === "done"
                          ? "bg-green-400"
                          : j.status === "failed"
                          ? "bg-red-400"
                          : "bg-gray-600"
                      }`}
                    />
                    <span className="font-mono text-xs text-gray-400">
                      {j.id}
                    </span>
                    <span
                      className={
                        STATUS_COLOR[j.status] || "text-gray-400"
                      }
                    >
                      {j.status}
                    </span>
                    <span className="ml-auto text-xs text-gray-600">
                      {j.created_at?.slice(0, 10)}
                    </span>
                  </button>
                  {j.running && (
                    <button
                      className="bg-red-800 hover:bg-red-700 rounded px-2 py-0.5 text-xs"
                      onClick={async () => {
                        try { await killJob(j.id); } catch {}
                        onRefresh();
                      }}
                    >
                      kill
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
