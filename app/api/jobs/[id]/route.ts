import { engineUrl, spaceFetch } from "@/lib/space";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await spaceFetch(`/api/v1/jobs/${encodeURIComponent(id)}`);
  if (!res.ok) return res;
  const job = await res.json();
  // Audio is served straight from the engine via a signed, expiring link (keeps big files off Vercel).
  if (job.result?.audio) job.result.audio = `${await engineUrl()}${job.result.audio}`;
  return Response.json(job);
}
