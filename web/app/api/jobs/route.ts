import { spaceFetch } from "@/lib/space";

export async function POST(req: Request) {
  return spaceFetch("/api/v1/jobs", { method: "POST", body: await req.text() });
}
