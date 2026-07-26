from paddleocr import PaddleOCR
import logging
import gc

# Silenciar advertencias molestas en la consola
logging.getLogger("ppocr").setLevel(logging.WARNING)

class MotorOCR:
    def __init__(self):
        self.contador_llamadas = 0
        self._inicializar_modelo()

    def _inicializar_modelo(self):
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
        self.contador_llamadas += 1
        
        # PREVENCIÓN DE MEMORY LEAK (OOM) AGRESIVA:
        # Reducido de 500 a 50 para asegurar que nunca supere los 4GB de límite.
        if self.contador_llamadas % 50 == 0:
            print(f"♻️ [Anti-Memory Leak] Reiniciando motor OCR en la llamada {self.contador_llamadas} para liberar RAM...")
            del self.ocr
            gc.collect()
            self._inicializar_modelo()
            gc.collect()

        texto_extraido = ""
        try:
            resultados = self.ocr.ocr(ruta_imagen, cls=False)
            if resultados and resultados[0]: 
                for linea in resultados[0]:
                    texto_extraido += linea[1][0] + " "
            
            resultados = None
            
            return texto_extraido.strip()
        except Exception as e:
            print(f"❌ Error al leer imagen {ruta_imagen}: {e}")
            return ""

_instancia_motor = None

def obtener_motor_ocr():
    global _instancia_motor
    if _instancia_motor is None:
        _instancia_motor = MotorOCR()
    return _instancia_motor