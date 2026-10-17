import React from "react";

export function MetricCardSkeleton() {
  return (
    <div className="metric-card-skeleton">
      <div className="skeleton-label" />
      <div className="skeleton-value" />
    </div>
  );
}

export function TrafficLightSkeleton() {
  return (
    <div className="metric-card-skeleton" style={{ height: "120px" }}>
      <div className="skeleton-label" style={{ width: "30%", marginBottom: "16px" }} />
      <div className="skeleton-value" style={{ width: "80%", height: "24px", marginBottom: "12px" }} />
      <div className="skeleton-value" style={{ width: "60%", height: "24px" }} />
    </div>
  );
}

export function ExecutiveSummarySkeleton() {
  return (
    <div className="metric-card-skeleton" style={{ height: "180px", display: "flex", flexDirection: "column", gap: "12px" }}>
      <div className="skeleton-label" style={{ width: "40%", height: "20px", marginBottom: "8px" }} />
      <div className="skeleton-value" style={{ width: "100%", height: "14px" }} />
      <div className="skeleton-value" style={{ width: "95%", height: "14px" }} />
      <div className="skeleton-value" style={{ width: "98%", height: "14px" }} />
      <div className="skeleton-value" style={{ width: "90%", height: "14px" }} />
    </div>
  );
}
