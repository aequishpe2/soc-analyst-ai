import AnalysisWorkspace from "./workspace";
export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <AnalysisWorkspace key={caseId} caseId={caseId} />;
}
