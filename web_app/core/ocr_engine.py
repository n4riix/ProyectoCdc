from paddleocr import PaddleOCR
import logging
import gc

# Silenciar advertencias molestas en la consola
logging.getLogger("ppocr").setLevel(logging.WARNING)

class MotorOCR:
    def __init__(self):
        print("⚙️ Encendiendo Motor OCR (Modo CPU Intel)...")
        self.ocr = PaddleOCR(
            use_angle_cls=False, 
            lang='es', 
            use_gpu=False,       # Desactivamos GPU por estabilidad térmica
            enable_mkldnn=True,  # Aceleración matemática de CPU
            cpu_threads=4
        )

    def extraer_texto(self, ruta_imagen):
        """Lee una imagen física y retorna todo el texto extraído como un string."""
        texto_extraido = ""
        try:
            resultados = self.ocr.ocr(ruta_imagen, cls=False)
            if resultados and resultados[0]: 
                for linea in resultados[0]:
                    texto_extraido += linea[1][0] + " "
            
            # Limpieza de memoria instantánea para evitar Memory Leaks
            resultados = None
            gc.collect()
            
            return texto_extraido.strip()
        except Exception as e:
            print(f"❌ Error al leer imagen {ruta_imagen}: {e}")
            return ""