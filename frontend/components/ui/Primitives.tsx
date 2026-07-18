import Link from "next/link";

export function LoadingCard({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="card">
      <p className="muted">{message}</p>
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="card card-error" role="alert">
      <p className="error-text">{message}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="empty-state">
      <p className="empty-title">{title}</p>
      {description && <p className="muted">{description}</p>}
    </div>
  );
}

export function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="section">
      <div className="section-header">
        <h2 className="section-title">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "completed" || status === "resolved" || status === "approved"
      ? "badge-ok"
      : status === "failed" || status === "rejected" || status === "firing"
        ? "badge-bad"
        : status === "running" || status === "open" || status === "pending"
          ? "badge-warn"
          : "badge-neutral";

  return <span className={`badge ${tone}`}>{status}</span>;
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-title">{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {actions}
    </header>
  );
}

export function DataList<T>({
  items,
  renderItem,
  emptyTitle,
  emptyDescription,
}: {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  emptyTitle: string;
  emptyDescription?: string;
}) {
  if (items.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return <ul className="data-list">{items.map(renderItem)}</ul>;
}

export function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="text-link">
      ← {label}
    </Link>
  );
}
