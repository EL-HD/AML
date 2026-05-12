from backend.database import engine
from sqlalchemy import inspect, text

def diagnose():
    print("--- Diagnóstico de Base de Datos ---")
    try:
        with engine.connect() as conn:
            print("✅ Conexión exitosa a la base de datos.")
            
            # Verificar tablas
            inspector = inspect(engine)
            tables = inspector.get_table_names(schema="public")
            print(f"Tablas encontradas: {tables}")
            
            if "Licencias" in tables:
                columns = [c["name"] for c in inspector.get_columns("Licencias", schema="public")]
                print(f"Columnas en 'Licencias': {columns}")
                
                # Verificar si hay datos
                res = conn.execute(text('SELECT count(*) FROM public."Licencias"'))
                count = res.scalar()
                print(f"Total de registros: {count}")
                
                if count > 0:
                    res = conn.execute(text('SELECT * FROM public."Licencias" LIMIT 1'))
                    row = res.fetchone()
                    print(f"Primer registro (ejemplo): {row}")
            else:
                print("❌ La tabla 'Licencias' no existe en el esquema public.")
                
    except Exception as e:
        print(f"❌ Error durante el diagnóstico: {e}")

if __name__ == "__main__":
    diagnose()
