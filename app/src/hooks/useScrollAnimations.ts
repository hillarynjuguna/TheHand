import { useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

export function useScrollAnimations() {
  useEffect(() => {
    const ctx = gsap.context(() => {
      // How It Works cards
      gsap.utils.toArray<HTMLElement>('.hiw-card').forEach((card, i) => {
        gsap.from(card, {
          y: 60,
          opacity: 0,
          duration: 0.9,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: card,
            start: 'top 80%',
            toggleActions: 'play none none none',
          },
          delay: i * 0.15,
        });
      });

      // Feature cards
      gsap.utils.toArray<HTMLElement>('.feature-card').forEach((card, i) => {
        gsap.from(card, {
          y: 50,
          opacity: 0,
          duration: 0.8,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: card,
            start: 'top 80%',
            toggleActions: 'play none none none',
          },
          delay: i * 0.1,
        });
      });

      // Terminal section
      const terminal = document.querySelector('.terminal-card');
      if (terminal) {
        gsap.from(terminal, {
          y: 80,
          opacity: 0,
          duration: 1.0,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: terminal,
            start: 'top 80%',
            toggleActions: 'play none none none',
          },
        });
      }

      // Architecture pipeline nodes
      gsap.utils.toArray<HTMLElement>('.pipeline-node').forEach((node, i) => {
        gsap.from(node, {
          x: -30,
          opacity: 0,
          duration: 0.6,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: '.pipeline-container',
            start: 'top 80%',
            toggleActions: 'play none none none',
          },
          delay: i * 0.12,
        });
      });

      // Model table
      const modelTable = document.querySelector('.model-table');
      if (modelTable) {
        gsap.from(modelTable, {
          y: 40,
          opacity: 0,
          duration: 0.8,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: modelTable,
            start: 'top 80%',
            toggleActions: 'play none none none',
          },
        });
      }
    });

    return () => ctx.revert();
  }, []);
}
