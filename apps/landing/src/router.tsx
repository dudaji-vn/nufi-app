import { createRootRoute, createRoute, createRouter, type RouterHistory } from '@tanstack/react-router';
import { RootLayout } from './routes/root';
import { Home } from './routes/home';
import { BlogIndex } from './routes/blog-index';
import { BlogPost } from './routes/blog-post';

const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: Home });
const blogRoute = createRoute({ getParentRoute: () => rootRoute, path: '/blog', component: BlogIndex });
const postRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/blog/$slug',
  component: BlogPost,
});

const routeTree = rootRoute.addChildren([indexRoute, blogRoute, postRoute]);

// The browser uses the default history; the build-time prerender (entry-server.tsx) passes a memory history.
// Scroll restoration is browser-only (on the server it would put an inline <script> into the static HTML).
export const createAppRouter = (history?: RouterHistory) =>
  createRouter({
    routeTree,
    history,
    defaultPreload: 'intent',
    scrollRestoration: !history,
  });

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
