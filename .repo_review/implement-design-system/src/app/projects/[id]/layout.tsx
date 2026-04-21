import { ProjectLayoutAsync } from "@/components/ProjectLayoutClient";

export default function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  return <ProjectLayoutAsync params={params}>{children}</ProjectLayoutAsync>;
}
