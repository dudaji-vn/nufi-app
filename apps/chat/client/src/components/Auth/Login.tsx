import { useOutletContext } from 'react-router-dom';
import { useAuthContext } from '~/hooks/AuthContext';
import type { TLoginLayoutContext } from '~/common';
import { ErrorMessage } from '~/components/Auth/ErrorMessage';
import { getLoginError } from '~/utils';
import { useLocalize } from '~/hooks';
import LoginForm from './LoginForm';

function Login() {
  const localize = useLocalize();
  const { error, setError, login } = useAuthContext();
  const { startupConfig } = useOutletContext<TLoginLayoutContext>();

  return (
    <>
      {error && <ErrorMessage>{localize(getLoginError(error))}</ErrorMessage>}
      {startupConfig?.emailLoginEnabled && (
        <LoginForm
          onSubmit={login}
          startupConfig={startupConfig}
          error={error}
          setError={setError}
        />
      )}
    </>
  );
}

export default Login;
