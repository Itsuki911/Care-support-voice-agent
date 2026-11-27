import { getDashboard } from "./dashboard-data";
import DashboardView from "./dashboard-view";

export const dynamic = "force-dynamic";
export default async function Dashboard({ searchParams }: { searchParams: Promise<{ from?: string; to?: string }> }) {
  const { from, to } = await searchParams;
  return <DashboardView data={await getDashboard(from, to)} />;
}
