/** Marca de FinanzAR: marca gráfica + logo. */

import type { JSX } from "react";

export function BrandMark({ className }: { className?: string }): JSX.Element {
  return (
    <div className={`brand-mark ${className ?? ""}`} aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  );
}

export function BrandLockup(): JSX.Element {
  return (
    <div className="brand-lockup">
      <BrandMark />
      <div>
        <strong>FinanzAR</strong>
        <small>LOCAL</small>
      </div>
    </div>
  );
}