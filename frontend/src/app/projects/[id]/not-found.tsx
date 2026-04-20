import Link from "next/link";

export default function ProjectNotFound() {
  return (
    <main className="flex-1 flex items-center justify-center px-vs-8">
      <div className="flex flex-col items-center gap-vs-3 text-center max-w-[520px]">
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
          Project
        </div>
        <h1 className="font-headline text-headline-lg font-medium">
          Model not indexed
        </h1>
        <p className="text-body-md text-on-surface-variant">
          The requested project isn&apos;t in your repository — it may have been
          deleted, or you&apos;re looking at a link from a different workspace.
        </p>
        <Link
          href="/"
          className="h-9 px-vs-4 rounded-sm bg-on-surface text-on-primary font-medium inline-flex items-center"
        >
          Return to projects
        </Link>
      </div>
    </main>
  );
}
