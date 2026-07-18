import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page">
      <section className="hero">
        <h1 className="title">Page not found</h1>
        <p className="subtitle">This page doesn&apos;t exist.</p>
        <Link href="/" className="health-endpoint">
          ← Back home
        </Link>
      </section>
    </main>
  );
}
