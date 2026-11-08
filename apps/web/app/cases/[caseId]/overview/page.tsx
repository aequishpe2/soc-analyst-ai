import Overview from "./workspace";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ caseId: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const { caseId } = await params;
  const { run } = await searchParams;
  return <Overview caseId={caseId} runId={run} />;
}
