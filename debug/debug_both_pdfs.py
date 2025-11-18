"""
Script per analizzare entrambi i PDF contemporaneamente
"""
import subprocess
import sys

if __name__ == "__main__":
    print("Analizzando contabile.pdf...")
    subprocess.run([sys.executable, "debug_pdf.py", "contabile.pdf"])
    
    print("\n\n" + "="*80)
    print("Analizzando estratto_conto.pdf...")
    print("="*80 + "\n")
    
    subprocess.run([sys.executable, "debug_pdf.py", "estratto_conto.pdf"])


