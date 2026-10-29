import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router';
import { RootLayout } from './routes/root';
import { Home } from './routes/home';
import { BlogIndex } from './routes/blog-index';
import { BlogPost } from './routes/blog-post';

const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: Home });
const blogRoute = createRoute({ getParentRoute: () => rootRoute, path: '/blog', component: BlogIndex });
const postRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/blog/hr-private-document-qa',
  component: BlogPost,
});

const routeTree = rootRoute.addChildren([indexRoute, blogRoute, postRoute]);

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  scrollRestoration: true,
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
