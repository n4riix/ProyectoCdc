import os
import logging
import gc
import cv2

# Silenciar advertencias molestas en la consola
logging.getLogger("ppocr").setLevel(logging.WARNING)
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

class MotorOCR:
    def __init__(self):
        self.contador_llamadas = 0
        self.modo_motor = "CPU"
        self.reader = None
        self._inicializar_modelo()

    def _inicializar_modelo(self):
        use_gpu_env = os.environ.get('USE_GPU', 'true').lower() in ('true', '1', 'yes')

        # Intento 1: EasyOCR GPU CUDA
        if use_gpu_env:
            try:
                import torch
                if torch.cuda.is_available():
                    import easyocr
                    device_name = torch.cuda.get_device_name(0)
                    print(f"⚡ Encendiendo Motor OCR Acelerado por GPU NVIDIA CUDA ({device_name})...")
                    self.reader = easyocr.Reader(['es'], gpu=True)
                    self.modo_motor = "EASYOCR_GPU"
                    return
            except Exception as e:
                print(f"⚠️ EasyOCR GPU no disponible ({e}). Intentando fallback...")

        # Intento 2: EasyOCR CPU
        try:
            import easyocr
            print("⚙️ Encendiendo Motor OCR (Modo CPU EasyOCR)...")
            self.reader = easyocr.Reader(['es'], gpu=False)
            self.modo_motor = "EASYOCR_CPU"
            return
        except Exception as e:
            print(f"⚠️ EasyOCR CPU no disponible ({e}). Intentando PaddleOCR...")

        # Intento 3: PaddleOCR CPU
        try:
            from paddleocr import PaddleOCR
            threads = int(os.environ.get('OCR_CPU_THREADS', '2'))
            print(f"⚙️ Encendiendo Motor OCR (Modo PaddleOCR CPU - {threads} hilos)...")
            self.reader = PaddleOCR(use_angle_cls=False, lang='es', use_gpu=False, enable_mkldnn=True, cpu_threads=threads)
            self.modo_motor = "PADDLE_CPU"
            return
        except Exception as e:
            print(f"❌ Error grave al inicializar motores OCR: {e}")
            self.modo_motor = "NINGUNO"

    def extraer_texto(self, ruta_imagen):
        """Lee una imagen física (o TIF multipágina) y retorna todo el texto extraído."""
        self.contador_llamadas += 1

        if self.contador_llamadas % 100 == 0:
            if self.modo_motor == "EASYOCR_GPU":
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:
                    pass
            gc.collect()

        texto_extraido = []
        try:
            if "EASYOCR" in self.modo_motor and self.reader:
                try:
                    from PIL import Image, ImageSequence
                    import numpy as np
                    im = Image.open(ruta_imagen)
                    for page in ImageSequence.Iterator(im):
                        page_rgb = page.convert('RGB')
                        img_np = np.array(page_rgb)
                        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                        res = self.reader.readtext(img_bgr, detail=0, canvas_size=1280)
                        texto_extraido.append(" ".join(res))
                except Exception as ex_pil:
                    img_cv = cv2.imread(ruta_imagen)
                    if img_cv is not None:
                        res = self.reader.readtext(img_cv, detail=0, canvas_size=1280)
                        texto_extraido.append(" ".join(res))
            elif self.modo_motor == "PADDLE_CPU" and self.reader:
                try:
                    from PIL import Image, ImageSequence
                    import numpy as np
                    im = Image.open(ruta_imagen)
                    if getattr(im, 'n_frames', 1) > 1:
                        # TIF Multipágina: procesar cada página
                        for page in ImageSequence.Iterator(im):
                            page_rgb = page.convert('RGB')
                            img_np = np.array(page_rgb)
                            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                            res = self.reader.ocr(img_bgr, cls=False)
                            if res and res[0]:
                                for linea in res[0]:
                                    texto_extraido.append(linea[1][0])
                    else:
                        # Página única: lectura directa rápida
                        resultados = self.reader.ocr(ruta_imagen, cls=False)
                        if resultados and resultados[0]:
                            for linea in resultados[0]:
                                texto_extraido.append(linea[1][0])
                except Exception as ex_pil:
                    # Fallback directo
                    resultados = self.reader.ocr(ruta_imagen, cls=False)
                    if resultados and resultados[0]:
                        for linea in resultados[0]:
                            texto_extraido.append(linea[1][0])
            
            return " ".join(texto_extraido).strip()
        except Exception as e:
            print(f"❌ Error al extraer texto de {ruta_imagen}: {e}")
            return ""

_instancia_motor = None

def obtener_motor_ocr():
    global _instancia_motor
    if _instancia_motor is None:
        _instancia_motor = MotorOCR()
    return _instancia_motor