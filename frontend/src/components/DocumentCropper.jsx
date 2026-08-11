import { useEffect, useRef, useState } from "react";
import { Loader2, Crop } from "lucide-react";
import { Button } from "@/components/ui/button";

const ORDER = ["topLeftCorner", "topRightCorner", "bottomRightCorner", "bottomLeftCorner"];

export default function DocumentCropper({ file, scanner, onConfirm, onCancel }) {
  const [imgUrl, setImgUrl] = useState(null);
  const [dims, setDims] = useState(null);
  const [corners, setCorners] = useState(null);
  const [autoDetected, setAutoDetected] = useState(true);
  const [processing, setProcessing] = useState(false);
  const imgRef = useRef(null);
  const svgRef = useRef(null);
  const dragRef = useRef(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setImgUrl(url);
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      const W = img.naturalWidth;
      const H = img.naturalHeight;
      setDims({ w: W, h: H });
      let pts = null;
      try {
        if (scanner && window.cv) {
          const canvas = document.createElement("canvas");
          canvas.width = W;
          canvas.height = H;
          canvas.getContext("2d").drawImage(img, 0, 0);
          const mat = window.cv.imread(canvas);
          const contour = scanner.findPaperContour(mat);
          if (contour) {
            pts = scanner.getCornerPoints(contour);
            if (contour.delete) contour.delete();
          }
          mat.delete();
        }
      } catch {
        pts = null;
      }
      const valid = pts && ORDER.every((k) => pts[k] && Number.isFinite(pts[k].x) && Number.isFinite(pts[k].y));
      let area = 0;
      if (valid) {
        const p = ORDER.map((k) => pts[k]);
        for (let i = 0; i < 4; i++) {
          const a = p[i];
          const b = p[(i + 1) % 4];
          area += a.x * b.y - b.x * a.y;
        }
        area = Math.abs(area / 2);
      }
      if (valid && area > W * H * 0.08) {
        setCorners(ORDER.map((k) => ({ x: pts[k].x, y: pts[k].y })));
        setAutoDetected(true);
      } else {
        const mx = W * 0.06;
        const my = H * 0.06;
        setCorners([{ x: mx, y: my }, { x: W - mx, y: my }, { x: W - mx, y: H - my }, { x: mx, y: H - my }]);
        setAutoDetected(false);
      }
    };
    img.src = url;
    return () => URL.revokeObjectURL(url);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  const toImageCoords = (e) => {
    const rect = svgRef.current.getBoundingClientRect();
    return {
      x: Math.min(Math.max(((e.clientX - rect.left) / rect.width) * dims.w, 0), dims.w),
      y: Math.min(Math.max(((e.clientY - rect.top) / rect.height) * dims.h, 0), dims.h),
    };
  };

  const startDrag = (i) => (e) => {
    e.preventDefault();
    dragRef.current = i;
    svgRef.current?.setPointerCapture?.(e.pointerId);
  };
  const onMove = (e) => {
    if (dragRef.current == null) return;
    const p = toImageCoords(e);
    const i = dragRef.current;
    setCorners((cs) => cs.map((c, j) => (j === i ? p : c)));
  };
  const endDrag = () => {
    dragRef.current = null;
  };

  const confirm = () => {
    setProcessing(true);
    try {
      const [tl, tr, br, bl] = corners;
      const d = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
      const w = Math.max(80, Math.round(Math.max(d(tl, tr), d(bl, br))));
      const h = Math.max(80, Math.round(Math.max(d(tl, bl), d(tr, br))));
      const pts = { topLeftCorner: tl, topRightCorner: tr, bottomRightCorner: br, bottomLeftCorner: bl };
      const out = scanner.extractPaper(imgRef.current, w, h, pts);
      out.toBlob(
        (blob) => {
          if (blob) onConfirm(new File([blob], `scan-${Date.now()}.jpg`, { type: "image/jpeg" }));
          else onConfirm(file);
        },
        "image/jpeg",
        0.92
      );
    } catch {
      onConfirm(file);
    }
  };

  if (!dims || !corners) {
    return (
      <div className="flex flex-col items-center gap-3 py-12" data-testid="scan-crop-loading">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        <p className="text-sm font-medium text-slate-700">Détection des contours du document…</p>
      </div>
    );
  }

  const r = Math.max(dims.w, dims.h) * 0.02;
  const sw = Math.max(2, dims.w * 0.004);

  return (
    <div className="space-y-3" data-testid="scan-crop-step">
      {!autoDetected && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800" data-testid="crop-manual-notice">
          Détection automatique impossible — ajustez les 4 coins manuellement.
        </div>
      )}
      <div className="flex justify-center overflow-hidden rounded-xl border border-slate-200 bg-slate-900 p-2">
        <div className="relative">
          <img src={imgUrl} alt="Document à recadrer" className="block h-auto max-h-[52vh] w-auto max-w-full select-none" draggable={false} />
          <svg
            ref={svgRef}
            viewBox={`0 0 ${dims.w} ${dims.h}`}
            className="absolute inset-0 h-full w-full touch-none"
            onPointerMove={onMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            data-testid="crop-overlay"
          >
            <polygon
              points={corners.map((c) => `${c.x},${c.y}`).join(" ")}
              fill="rgba(16,185,129,0.15)"
              stroke="#10b981"
              strokeWidth={sw}
            />
            {corners.map((c, i) => (
              <circle
                key={i}
                cx={c.x}
                cy={c.y}
                r={r}
                fill="white"
                stroke="#10b981"
                strokeWidth={sw * 1.5}
                style={{ cursor: "move" }}
                onPointerDown={startDrag(i)}
                data-testid={`crop-handle-${i}`}
              />
            ))}
          </svg>
        </div>
      </div>
      <p className="text-center text-xs text-slate-400">
        Déplacez les coins pour ajuster le cadre — la perspective sera corrigée automatiquement.
      </p>
      <div className="flex flex-col-reverse justify-end gap-2 border-t border-slate-100 pt-4 sm:flex-row">
        <Button variant="outline" data-testid="crop-cancel-btn" onClick={onCancel}>Reprendre la photo</Button>
        <Button data-testid="crop-confirm-btn" onClick={confirm} disabled={processing} className="gap-2 bg-slate-900 hover:bg-slate-800">
          {processing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Crop className="h-4 w-4" />} Valider le recadrage
        </Button>
      </div>
    </div>
  );
}
