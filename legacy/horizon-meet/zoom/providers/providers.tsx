"use client";

import { ReactNode } from "react";
import { Toaster } from "react-hot-toast"; // or sonner if you switched

export function Providers({ children }: { children: ReactNode }) {
  return (
    <>
      <Toaster />
      {children}
    </>
  );
}
