import ImportWorkspace from "./workspace";
export default async function CasePage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <ImportWorkspace caseId={caseId} />;
}
