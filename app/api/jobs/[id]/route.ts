import { SPACE_URL, spaceFetch } from "@/lib/space";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await spaceFetch(`/api/v1/jobs/${encodeURIComponent(id)}`);
  if (!res.ok) return res;
  const job = await res.json();
  // Audio is served straight from the Space via a signed, expiring link (keeps big files off Vercel).
  if (job.result?.audio) job.result.audio = `${SPACE_URL}${job.result.audio}`;
  return Response.json(job);
}
