"use client";

import type { TimelineItem } from "@/lib/api";

export default function TimelineSection({ timeline }: { timeline: TimelineItem[] }) {
  if (timeline.length === 0) {
    return <p className="muted">No timeline events for this run.</p>;
  }

  return (
    <ol className="timeline">
      {timeline.map((event) => (
        <li key={event.id} className="timeline-item">
          <time className="muted small">
            {event.event_time
              ? new Date(event.event_time).toLocaleString()
              : "Unknown time"}
          </time>
          <strong>{event.title}</strong>
          {event.description && <p>{event.description}</p>}
          {(event.source || event.event_type) && (
            <p className="muted small">
              {[event.source, event.event_type].filter(Boolean).join(" · ")}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
