'use client';

import { useEffect, useState } from "react";
import Particles, { initParticlesEngine } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";
import type { Engine } from "@tsparticles/engine";

export default function NeuralGlow() {
  const [init, setInit] = useState(false);

  useEffect(() => {
    initParticlesEngine(async (engine: Engine) => {
      await loadSlim(engine);
    }).then(() => {
      setInit(true);
    });
  }, []);

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {/* MUCH BRIGHTER GRADIENTS */}
      <div 
        className="absolute -top-40 -left-40 w-[1000px] h-[1000px] bg-blue-500/60 rounded-full blur-[200px] animate-pulse"
        style={{ animationDuration: '4s' }}
      />
      
      <div 
        className="absolute -bottom-40 -right-40 w-[1200px] h-[1200px] bg-purple-500/55 rounded-full blur-[200px] animate-pulse" 
        style={{ animationDuration: '5s', animationDelay: '1s' }}
      />
      
      <div 
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1100px] h-[1100px] bg-gradient-to-br from-cyan-400/45 via-pink-400/40 to-purple-500/45 rounded-full blur-[180px] animate-pulse" 
        style={{ animationDuration: '6s', animationDelay: '2s' }}
      />

      {/* Neural network particles - MORE VISIBLE */}
      {init && (
        <Particles
          className="absolute inset-0"
          options={{
            background: {
              color: "transparent",
            },
            fullScreen: false,
            fpsLimit: 60,
            particles: {
              color: { 
                value: ["#3b82f6", "#8b5cf6", "#06b6d4"] 
              },
              links: {
                color: "#3b82f6",
                distance: 150,
                enable: true,
                opacity: 0.4, // Increased from 0.2
                width: 2, // Increased from 1
              },
              move: {
                enable: true,
                speed: 0.5,
                direction: "none",
                random: true,
                straight: false,
                outModes: {
                  default: "bounce",
                },
              },
              number: {
                value: 80, // Increased from 60
                density: {
                  enable: true,
                },
              },
              opacity: {
                value: 0.5, // Increased from 0.3
              },
              size: {
                value: { min: 2, max: 4 }, // Increased from 1-3
              },
            },
            detectRetina: true,
          }}
        />
      )}

      {/* Grid overlay - MORE VISIBLE */}
      <div 
        className="absolute inset-0 opacity-10"
        style={{
          backgroundImage: `
            repeating-linear-gradient(
              0deg,
              rgba(59, 130, 246, 0.5) 0px,
              transparent 1px,
              transparent 50px,
              rgba(59, 130, 246, 0.5) 51px
            ),
            repeating-linear-gradient(
              90deg,
              rgba(147, 51, 234, 0.5) 0px,
              transparent 1px,
              transparent 50px,
              rgba(147, 51, 234, 0.5) 51px
            )
          `
        }}
      />
    </div>
  );
}
