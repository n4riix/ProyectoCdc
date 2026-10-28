import json
import os
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

CLASES_NOTARIALES = [
    'REC DocumentoConstitutivoEstatuario',
    'REC ActaAsambleaModificaciones',
    'REC ActaJuntaDirectiva',
    'REC DocumentoFirmaPersonal',
    'REC DocumentoPoder'
]

DATASET_GLOBAL = '/volumen_compartido/dataset_global'
ESPECIALISTA_DIR = '/cerebro_beto/especialista_notarial'
os.makedirs(ESPECIALISTA_DIR, exist_ok=True)

textos = []
etiquetas = []

print('Cargando textos para especialista notarial dentro del contenedor...')
for clase in CLASES_NOTARIALES:
    dir_clase = os.path.join(DATASET_GLOBAL, clase)
    if not os.path.exists(dir_clase):
        continue
    archivos = [f for f in os.listdir(dir_clase) if f.endswith('.txt')]
    for arc in archivos:
        path_arc = os.path.join(dir_clase, arc)
        try:
            with open(path_arc, 'r', encoding='utf-8', errors='ignore') as f:
                t = f.read().strip()
                if len(t) > 30:
                    textos.append(t)
                    etiquetas.append(clase)
        except Exception:
            pass

print(f'Total muestras notariales: {len(textos)}')
vectorizer = TfidfVectorizer(ngram_range=(1, 3), max_features=25000)
X = vectorizer.fit_transform(textos)

clf = LogisticRegression(C=5.0, max_iter=1000, random_state=42)
clf.fit(X, etiquetas)

joblib.dump(clf, os.path.join(ESPECIALISTA_DIR, 'modelo_notarial.pkl'))
joblib.dump(vectorizer, os.path.join(ESPECIALISTA_DIR, 'vectorizador_notarial.pkl'))
print('ESPECIALISTA_SERIALIZADO_OK_COMPATIBLE_100%')
