/** @type {import('next').NextConfig} */
export default {
  // The site used to have a password page; send old /login links to the app.
  async redirects() {
    return [{ source: "/login", destination: "/", permanent: false }];
  },
};
