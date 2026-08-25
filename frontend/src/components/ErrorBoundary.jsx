import { Component } from "react";
import { AlertTriangle } from "lucide-react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div data-testid="error-boundary"
          className="flex flex-col items-center gap-3 rounded-2xl border border-red-200 bg-red-50 px-6 py-16 text-center">
          <AlertTriangle className="h-8 w-8 text-red-500" />
          <p className="text-sm font-semibold text-red-800">Une erreur est survenue sur cette page.</p>
          <p className="text-xs text-red-600">Vos données ne sont pas affectées.</p>
          <button data-testid="error-boundary-reload-btn"
            onClick={() => window.location.reload()}
            className="mt-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800">
            Recharger la page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
