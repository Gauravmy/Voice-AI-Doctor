import { Dashboard } from "@/components/Dashboard";

// The dashboard is fully client-rendered: all data comes live from the FastAPI
// backend (REST + WebSocket), so there is nothing to render or cache on the server.
export default function Home() {
  return <Dashboard />;
}
