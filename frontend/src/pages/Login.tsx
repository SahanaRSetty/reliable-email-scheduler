import "./Login.css";

function Login() {
  const handleGoogleLogin = () => {
    window.location.href = "http://localhost:8000/auth/google/login";
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-icon">
          ✉
        </div>

        <h1>Reliable Email Scheduler</h1>

        <p className="login-subtitle">
          Schedule. Deliver. Recover. Reliably.
        </p>

        <button
          className="google-login-button"
          onClick={handleGoogleLogin}
        >
          <span className="google-icon">G</span>
          Continue with Google
        </button>

        <p className="login-security">
          Secure authentication powered by Google
        </p>
      </div>
    </div>
  );
}

export default Login;