import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('React ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-10 font-sans">
          <h1 className="text-red-600 text-xl font-semibold mb-2">
            Something went wrong
          </h1>
          <p className="text-gray-500 text-sm">
            An unexpected error occurred. Please try reloading the page.
          </p>
          {import.meta.env.DEV && (
            <>
              <pre className="text-gray-500 text-sm whitespace-pre-wrap mt-3">
                {this.state.error?.message}
              </pre>
              <pre className="text-gray-400 text-xs whitespace-pre-wrap mt-2">
                {this.state.error?.stack}
              </pre>
            </>
          )}
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-orange-500 text-white text-sm font-medium rounded-lg hover:bg-orange-600 transition-colors cursor-pointer"
          >
            Reload Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
