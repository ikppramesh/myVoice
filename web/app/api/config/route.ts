import { SPACE_URL } from "@/lib/space";

// The studio (record / create voices) is the Gradio UI on the Space, behind its own password.
export const GET = () => Response.json({ studioUrl: SPACE_URL });
