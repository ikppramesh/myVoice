// Where to record / manage voices. The studio UI isn't exposed through the tunnel, so this is the
// engine machine's local address (e.g. http://127.0.0.1:7860); the link only works on that machine.
export const GET = () => Response.json({ studioUrl: process.env.STUDIO_URL || "" });
