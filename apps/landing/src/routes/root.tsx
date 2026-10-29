import { Outlet } from '@tanstack/react-router';
import { Sprite } from '../components/sprite';
import { Nav } from '../components/nav';
import { Footer } from '../components/footer';

export function RootLayout() {
  return (
    <>
      <Sprite />
      <Nav />
      <Outlet />
      <Footer />
    </>
  );
}
