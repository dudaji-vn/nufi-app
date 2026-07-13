import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RecoilRoot } from 'recoil';
import type { TUser } from 'librechat-data-provider';
import AccountSettings from '../AccountSettings';

const queryClient = new QueryClient();

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={queryClient}>
      <RecoilRoot>{ui}</RecoilRoot>
    </QueryClientProvider>,
  );
}

const mockUser: TUser = {
  id: 'user-1',
  username: 'tester',
  email: 'tester@example.com',
  name: 'Tester',
  avatar: '',
  role: 'USER',
  provider: 'local',
  createdAt: '',
  updatedAt: '',
};

jest.mock('~/hooks/AuthContext', () => ({
  useAuthContext: () => ({
    user: mockUser,
    isAuthenticated: true,
    logout: jest.fn(),
  }),
}));

jest.mock('~/data-provider', () => ({
  useGetStartupConfig: () => ({ data: undefined }),
  useGetUserBalance: () => ({ data: undefined }),
}));

describe('AccountSettings', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('toggles UI mode from the account menu', async () => {
    renderWithProviders(<AccountSettings />);

    fireEvent.click(screen.getByTestId('nav-user'));

    const item = await screen.findByTestId('account-ui-mode-toggle');
    fireEvent.click(item);

    expect(localStorage.getItem('uiMode')).toBe(JSON.stringify('advanced'));
  });
});
