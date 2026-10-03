import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-20 text-center">
      <p className="text-sm text-muted">404</p>
      <h2 className="mt-1 text-xl font-semibold">Page not found</h2>
      <Link href="/" className="mt-4 inline-block text-sm text-accent underline">
        Back to dashboard
      </Link>
    </div>
  );
}
