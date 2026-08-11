let loadPromise = null;

const inject = (src) =>
  new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`Chargement impossible: ${src}`));
    document.head.appendChild(s);
  });

const waitCvReady = () =>
  new Promise((resolve, reject) => {
    const cv = window.cv;
    if (!cv) return reject(new Error("OpenCV absent"));
    if (cv.Mat) return resolve();
    if (typeof cv.then === "function") {
      cv.then((mod) => {
        window.cv = mod;
        resolve();
      });
      return;
    }
    const timer = setTimeout(() => (window.cv?.Mat ? resolve() : reject(new Error("OpenCV timeout"))), 25000);
    cv.onRuntimeInitialized = () => {
      clearTimeout(timer);
      resolve();
    };
  });

export function loadDocScanner() {
  if (!loadPromise) {
    loadPromise = (async () => {
      if (!window.cv) await inject("/scanner/opencv.js");
      await waitCvReady();
      if (!window.jscanify) await inject("/scanner/jscanify.min.js");
      return new window.jscanify();
    })().catch((e) => {
      loadPromise = null;
      throw e;
    });
  }
  return loadPromise;
}
