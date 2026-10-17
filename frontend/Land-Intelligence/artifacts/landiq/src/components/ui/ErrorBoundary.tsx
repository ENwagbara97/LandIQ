import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error in ErrorBoundary:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full w-full p-6 text-center space-y-4 bg-background/50 backdrop-blur-sm rounded-2xl border border-destructive/20 text-destructive">
          <AlertCircle className="w-12 h-12 opacity-80" />
          <div className="space-y-1">
            <h3 className="font-semibold text-lg">Something went wrong</h3>
            <p className="text-sm opacity-80 max-w-[250px] mx-auto leading-relaxed">
              {this.props.fallbackMessage || "A component crashed while rendering."}
            </p>
          </div>
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-2 text-foreground border-border hover:bg-muted"
          >
            <RefreshCw className="w-4 h-4 mr-2" /> Try again
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
