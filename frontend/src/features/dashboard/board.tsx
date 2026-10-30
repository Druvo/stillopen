"use client";

import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCorners,
  type KeyboardCoordinateGetter,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useMemo, useState } from "react";
import type { Bucket, Job, StatusInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { JobCard, type CardExtras } from "./job-card";
import { jobsByBucket } from "./logic";

/** Arrow keys hop a held card to the neighbouring column (the default would nudge it 25px at a time). */
const columnKeyboard: KeyboardCoordinateGetter = (event, { context: { droppableRects, droppableContainers, over } }) => {
  if (event.code !== "ArrowLeft" && event.code !== "ArrowRight") return undefined;
  event.preventDefault();
  const columns = droppableContainers
    .getEnabled()
    .map((c) => ({ id: c.id, rect: droppableRects.get(c.id) }))
    .flatMap((c) => (c.rect ? [{ id: c.id, rect: c.rect }] : []))
    .sort((a, b) => a.rect.left - b.rect.left);
  const here = columns.findIndex((c) => c.id === over?.id);
  const next = columns[here + (event.code === "ArrowRight" ? 1 : -1)];
  return next ? { x: next.rect.left + 8, y: next.rect.top + 48 } : undefined;
};

type Common = {
  statuses: StatusInfo[];
  extras: CardExtras;
  onMove: (job: Job, statusId: number) => void;
  onCheckFit: (job: Job) => void;
  checkingId: number | null;
};

function DraggableCard({ job, ...common }: { job: Job } & Common) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, isDragging } = useDraggable({ id: job.id });
  return (
    <div ref={setNodeRef} className={cn(isDragging && "opacity-40")}>
      <JobCard
        job={job}
        statuses={common.statuses}
        extras={common.extras}
        onMove={common.onMove}
        onCheckFit={common.onCheckFit}
        checking={common.checkingId === job.id}
        variant="compact"
        dragHandle={{ attributes, listeners, setActivatorNodeRef }}
      />
    </div>
  );
}

function Column({ bucket, jobs, ...common }: { bucket: Bucket; jobs: Job[] } & Common) {
  const { setNodeRef, isOver } = useDroppable({ id: bucket.key });
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={`col-${bucket.key}`}
      className={cn("flex w-[85vw] max-w-80 shrink-0 snap-start flex-col rounded-xl border border-border bg-surface-2 p-2 transition-colors", isOver && "border-brand bg-surface")}
    >
      <header className="px-2 pb-2 pt-1">
        <h2 id={`col-${bucket.key}`} className="flex items-baseline justify-between text-sm font-semibold">
          {bucket.label}
          <span className="text-xs font-normal text-muted">{jobs.length}</span>
        </h2>
        {bucket.description && <p className="text-xs text-muted">{bucket.description}</p>}
      </header>
      <div className="flex min-h-24 flex-col gap-2">
        {jobs.map((job) => (
          <DraggableCard key={job.id} job={job} {...common} />
        ))}
        {jobs.length === 0 && <p className="px-2 py-6 text-center text-xs text-muted">Nothing here right now. That is fine.</p>}
      </div>
    </section>
  );
}

/** The board. Loaded only when the board view is shown (it brings the drag-and-drop library with it). */
export default function Board({ buckets, jobs, ...common }: { buckets: Bucket[]; jobs: Job[] } & Common) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: columnKeyboard }),
  );
  const grouped = useMemo(() => jobsByBucket(jobs, buckets), [jobs, buckets]);
  const [active, setActive] = useState<Job | null>(null);
  const byId = useMemo(() => new Map(jobs.map((j) => [j.id, j])), [jobs]);
  const bucketLabel = (key: string | number | undefined) => buckets.find((b) => b.key === key)?.label ?? "another column";

  const onDragStart = (event: DragStartEvent) => setActive(byId.get(Number(event.active.id)) ?? null);
  const onDragEnd = (event: DragEndEvent) => {
    setActive(null);
    const job = byId.get(Number(event.active.id));
    const target = event.over ? String(event.over.id) : null;
    if (!job || !target || target === job.bucket_key) return;
    const status = common.statuses.find((s) => s.bucket_key === target);
    if (status) common.onMove(job, status.id);
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => setActive(null)}
      accessibility={{
        announcements: {
          onDragStart: ({ active: a }) => `Picked up ${byId.get(Number(a.id))?.role ?? "job"}.`,
          onDragOver: ({ active: a, over }) => (over ? `${byId.get(Number(a.id))?.role ?? "Job"} is over ${bucketLabel(over.id)}.` : ""),
          onDragEnd: ({ active: a, over }) => (over ? `Dropped ${byId.get(Number(a.id))?.role ?? "job"} on ${bucketLabel(over.id)}.` : "Dropped outside a column; nothing changed."),
          onDragCancel: () => "Move cancelled.",
        },
        screenReaderInstructions: {
          draggable: "Press space or enter to pick up this job. Use the arrow keys to move between columns, space to drop, escape to cancel.",
        },
      }}
    >
      <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-4 lg:mx-0 lg:px-0">
        {buckets.map((bucket) => (
          <Column key={bucket.key} bucket={bucket} jobs={grouped[bucket.key] ?? []} {...common} />
        ))}
      </div>
      <DragOverlay>
        {active ? <JobCard job={active} statuses={common.statuses} extras={common.extras} onMove={common.onMove} onCheckFit={common.onCheckFit} checking={false} variant="compact" overlay /> : null}
      </DragOverlay>
    </DndContext>
  );
}
