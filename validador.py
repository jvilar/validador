'''
Created on 16/07/2014

@version 1.3.0 (2016-09-16)
@author: David Llorens (dllorens@uji.es)
         Federico Prat (fpart@uji.es)
         Juan Miguel Vilar (jvilar@uji.es)

1.3.0 - Reestructuración del código y cambio en el modo de funcionamiento para que
        pueda validar sólo un ejercicio.
1.2.10- Antes se llamaba a check_function_output_for_exception sin comprobar si
        se estaban validando funciones o no.
        Eliminados avisos de Eclipse por sangrado inesperado.
        NOTA: Cambios de fprat@uji.es
1.2.9 - Las excepciones que lanza valida_funciones.py dan más información al validador.
1.2.8 - Distingue ejercicios opcionales, que generan diagnóstico, pero no influyen en
        "superar" o "no superar" la validación ni aparecen en el posible zip.
        Se marcan en fichero de configuración con OPTIONAL tras nombre de ejercicio:
                           ... ["ej22.py", OPTIONAL, [...
        Correcciones ortográficas ("ejecutandose", "VALIDACION").
        NOTA: Cambios de fprat@uji.es
1.2.7 - Si al ir a generar el zip, falta algun *.py,  no se genera (daba error) y se 
        muestra un mensaje informado de que hay que crearlo, aunque esté vacío.
1.2.6 - Genera zip cuando el número de ejercicios que no superan las pruebas es inferior 
        o igual a un umbral.
1.2.5 - Corregio bugs en codecs
1.2.4 - Posibilidad de llamar al validador de funciones.
        Variable VALIDADOR_FUNCIONES en el fichero de configuración.
1.2.3 - Comprueba que el python sea el 3.1 o superior (el subprocess.check_output 
        apareció en esa versión).
1.2.2 - No trata de validar los ficheros ej<num>.py vacíos. Los muestra como una lista
        al finalizar la validación.
1.2.1 - Corrige bug .imagen
1.2.0 - Cambia el formato de los mensajes de error. Ahora se gestionan por líneas 
        (antes por palabras). Afecta al formato del fichero de configuración.
        No son válidos los ficheros de las prácticas 1 y 2.
1.1.2 - Soluciona problema cuando hay acentos en la entrada estándar.
1.1.1 - El validador define una variable de entorno. Se usa para el módulo de imágenes
        visualice o no los resultados en una ventana gráfica.
1.1.0 - Nuevo formato para la variable 'work' en el fichero .cfg
        Permite, además de validar la entrada estándar, validar un imagen resultado
        generada mediante 'mostrarImagen'. Cada prueba contiene los datos de entrada, 
        la salida correspondiente y, opcionalmente, el nombre del fichero que contiene
        la imagen resultado.
1.0.8 - Cuando la salida del programa no coincide con la esperada, indica la primera 
        palabra encontrada que no coincide con la palabra esperada
1.0.7 - El fichero 'validador_prac<num>.cfg tiene una nueva variable booleana CREATE_ZIP,
        que vale True por defecto (si no aparece). Permite inhibir la creación del zip.
        Útil cuando las pruebas no están completas.
      - Mejora los mensajes de error si el fichero de configuración no existe o tiene
        un formato erróneo.
1.0.6 - El validador ya es independiente de las prácticas. Debe haber un fichero 
        'validador_prac<num>.cfg junto a validador.py. Si no hay ninguno o hay más 
        de uno, avisa y no valida.
1.0.5 - Si se pasan todas las pruebas, se genera el ZIP de entrega en el escritorio 
      - Detecta excepciones lanzadas en el código de los programas evaluados
1.0.4 - Corrige bug en pruebas 17, 22 y 23 de la práctica 1
1.0.3 - Corrige bug al mostrar la versión de python utilizada
1.0.2 - El validador utiliza el python que lo ejecuta a él para validar 
1.0.1 - Bug corregido (utilizado timeout en python <= 3.3)

Comprobador simple de programas
-------------------------------
Si se ejecuta en Python 3.3 o superior utilizará timeouts al lanzar las ejecuciones.
Esto permite que programas mal construidos (p.e. con bucles infinitos) no bloqueen al
propio comprobador.
'''

import os
import subprocess
import zipfile
from sys import version_info, executable
import sys
import glob
import codecs


def error(m):
    print("ERROR:", m)
    sys.exit()

def clean(s):
    return " ".join(s.strip().lower().split())

def comparaSalida(user, out):
    lineasUser = [ clean(l) for l in user.split("\n") if l.strip()!="" ]
    lineasOut  = [ clean(l) for l in out.split("\n") if l.strip()!="" ]

    longitud = min(len(lineasUser), len(lineasOut))
    for i in range(longitud):
        if lineasUser[i] != lineasOut[i]:
            return True, lineasUser[i], lineasOut[i]

    if len(lineasUser) == len(lineasOut):
        return False, None, None
    elif len(lineasUser) > longitud:
        return True, "\n".join(lineasUser[longitud:]), None
    else:
        return True, None, "\n".join(lineasOut[longitud:])

def matriz(datos):
    lineas=datos.split('\n')
    mat=[]
    for l in lineas:
        if l=="": break
        mat.append([int(n) for n in l.split()])
    return mat

def compararMatrices(user, out):
    filasUser, colsUser = len(user), len(user[0])
    filasOut, colsOut = len(out), len(out[0])
    if filasUser != filasOut or colsUser != colsOut:
        return True, None
    for fila in range(len(user)):
        for col in range(len(user[0])):
            if user[fila][col] != out[fila][col]:
                return True, (fila, col, out[fila][col], user[fila][col])
    return False, None

def comprobarFichero(conf, image):
    resfilename = conf.RESULTDIR + image
    with open(resfilename) as f:
        user = matriz(f.read())
    try:
        with open(conf.IMAGEFILENAME) as f:
            out = matriz(f.read())
    except Exception:
        return True, None
    return compararMatrices(user, out)

def posDiferencia(cad1, cad2):
    if len(cad1) > len(cad2):
        cad1, cad2 = cad2, cad1
    for i in range(len(cad1)):
        if cad1[i] != cad2[i]:
            return i
    return len(cad1)

def checkOutput(filename, inp, out, image, res, conf):
    user = res.decode('utf8').strip()
    if len(inp)>0 and inp[-1]=="\n":
        entrada = inp[:-1].split("\n")
    else:
        entrada = inp.split("\n")
    hayDiferencias, encontrado, esperado = comparaSalida(user, out)
    if hayDiferencias:
        print("{0} FALLO para entrada {1}.".format(filename, entrada))
        if encontrado != None and esperado != None:
            print("    Se esperaba: {0}".format(esperado))
            print("    Encontrado : {0}".format(encontrado))
            print(" "*(posDiferencia(esperado,encontrado)+15)+"**^**")
            print()
        elif esperado!= None:
            print("La salida del programa no está completa. Faltan las siguientes líneas: ")
            print(esperado)
            print()
        else:
            print("El programa ha generado más líneas de las esperadas. Sobran las siguientes líneas: ")
            print(encontrado)
            print()
    ficherosDistintos = False
    if image != None:
        ficherosDistintos,  posicion = comprobarFichero(image, conf)
        if ficherosDistintos:
            if posicion == None:
                print("{0} FALLO para entrada {1}. Las dimensiones de la imagen resultado no coinciden con las esperadas".format(filename, entrada))
            else:
                fila, columna, encontrado, esperado = posicion
                print("{0} FALLO para entrada {1}. En la fila {2} y columna {3} se ha encontrado el valor {4} y se esperaba {5}".format(filename, inp.split(), fila, columna, encontrado, esperado))
    return not (hayDiferencias or ficherosDistintos)

def check_function_output(filename):
    with open(".funciones_output.txt","r",encoding="utf-8") as f:
        lineas = f.read()
        if len(lineas) == 0:
            return False
        print("Error en las funciones de", filename)
        print(lineas)
        return True

def check_function_output_for_exception(filename):
    with open(".funciones_output.txt","r",encoding="utf-8") as f:
        lineas = f.read().split("\n")
        if len(lineas) == 0:
            return False
        for l in lineas:
            print("\t",l)
        return True

def do_test(filename, inp, out, image, check_function, conf):
    programa = [executable, conf.VALIDADOR_FUNCIONES, filename] if check_function else [executable, filename]
    try:
        if version_info >= (3, 3):
            res = subprocess.check_output(programa, stdin=open('.fin'), timeout=conf.TIMEOUT)
        else:
            res = subprocess.check_output(programa, stdin=open('.fin'))
    except Exception as e:
        if version_info >= (3, 3) and isinstance(e, subprocess.TimeoutExpired):
            print("{0} TIMEOUT para entrada {1}".format(filename, inp.split()))
            return False
        print("{0} FALLO para entrada {1}. Lanzada excepción:".format(filename, inp.split()))
        if check_function: check_function_output_for_exception(filename)
        return False
    if check_function:
        if check_function_output(filename):
            return False
    return checkOutput(filename, inp, out, image, res, conf)

def esta_implementado(fichero):
    return os.path.isfile(fichero) and os.stat(fichero).st_size > 0

def validacion(conf):
    resultado = Resultado()
    for ejercicio in conf.ejercicios:
        prueba_ejercicio(conf, ejercicio, resultado)
    return resultado

def prueba_ejercicio(conf, ejercicio, resultado):
    filename = ejercicio.nombre
    if ejercicio.obligatorio:
        resultado.add_to_zip(filename)
    if not esta_implementado(filename):
        resultado.add_not_implemented(filename, ejercicio.obligatorio)
        return
    if ejercicio.pruebas == []:
        print("{0} no tiene pruebas (compruébalo manualmente)".format(filename))
        return
    isOk = True
    for pos, data in enumerate(ejercicio.pruebas):
        if len(data) == 2:
            inp, out = data
            image = None
        elif len(data) == 3:
            inp, out, image = data
        else:
            print("Formato de pruebas no válido para {0}".format(filename))
            isOk = False
            break
        with codecs.open(".fin", "w", "utf8") as in_file:
            in_file.write(inp)
        isOk = do_test(filename, inp, out, image, pos==0 and conf.VALIDADOR_FUNCIONES!="", conf)
        if not isOk:
            break
    if isOk:
        print("{0} pasa las pruebas".format(filename))
    else:
        resultado.add_not_valid(filename, ejercicio.obligatorio)

def get_desktop_folder():
    from os import path
    desktop = path.expanduser("~/Desktop")
    home = path.expanduser("~")
    if path.isdir(desktop):
        return desktop
    return home

class Resultado:
    def __init__(self):
        self.not_implemented_exercices = []
        self.not_implemented_mandatory_exercices = []
        self.not_valid_exercices = []
        self.not_valid_mandatory_exercices = []
        self.todas_las_pruebas_superadas = True
        self.todas_las_obligatorias_superadas = True
        self.to_be_zipped = []

    def add_to_zip(self, name):
        self.to_be_zipped.append(name)

    def add_not_implemented(self, name, mandatory):
        self.not_implemented_exercices.append(name)
        if mandatory:
            self.not_implemented_mandatory_exercices.append(name)
        self.add_not_valid(name, mandatory)

    def add_not_valid(self, name, mandatory):
        self.not_valid_exercices.append(name)
        self.todas_las_pruebas_superadas = False
        if mandatory:
            self.not_valid_mandatory_exercices.append(name)
            self.todas_las_obligatorias_superadas = False


class Configuración:
    fields = [("VERSION", "1.3.0"),
              ("TIMEOUT", 5), #seconds
              ("RESULTDIR", "resultados/"),
              ("IMAGEFILENAME", ".imagen.txt"),
              ("NUM_PRACTICA", -1),
              ("work", []),
              ("CREATE_ZIP", True),
              ("VALIDADOR_FUNCIONES", ""),
              ("NUM_MAX_EJERCICIOS_MAL", 0) # de los obligatorios
              ]

    def __init__(self, variables):
        self.variables = variables
        for (nombre, valor) in Configuración.fields:
            self.asigna(nombre, valor)

    def asigna(self, nombre, valor):
        v = self.variables.get(nombre, valor)
        if nombre != "work":
            setattr(self, nombre, v)
        else:
            self.ejercicios = [ Ejercicio(e) for e in v ]

class Ejercicio:
    def __init__(self, entrada):
        self.nombre = entrada[0]
        self.pruebas = entrada[-1]
        self.obligatorio = len(entrada) == 2 or entrada[1]

def lee_configuración():
    # busca el fichero de configuración del validador
    matching_files = glob.glob('./validador_prac[0-9].cfg')
    if len(matching_files) == 0:
        error("Falta el fichero de configuración del validador (validador_prac<num>.cfg). Copia a este directorio el que corresponda a esta práctica")
    elif len(matching_files)>1:
        error("Hay más de un fichero de configuración del validador (validador_prac<num>.cfg) en el directorio. Deja sólo el adecuado para esta práctica.")

    # carga el fichero de validación
    conf_file = matching_files[0]
    try:
        conf = open(conf_file, 'r', encoding="utf-8").read()
    except Exception as e:
        error("Fichero '{0}' no encontrado o no pudo abrirse".format(conf_file))

    variables = { "MANDATORY": True, # Usadas para marcar los ficheros
                  "OPTIONAL": False
            }
    # aplica (ejecuta) la coonfiguración
    try:
        exec(conf, variables)
    except Exception as e:
        error ("Formato erróneo en el fichero de configuración '{}'.\nExcepción:\n{}".format(conf_file, e))

    conf = Configuración(variables)

    # comprueba 'work'
    if len(conf.ejercicios)==0:
        error ("El fichero de configuración '{0}' no tiene ninguna prueba.".format(matching_files[0]))
    return conf

def crea_zip(conf, resultado):
    print("   GENERANDO ZIP DE ENTREGA...")

    ZIP_ENTREGA = "entrega_prac{0}.zip".format(conf.NUM_PRACTICA)
    carpeta_destino = get_desktop_folder()
    filename = carpeta_destino+"/"+ZIP_ENTREGA
    zf = zipfile.ZipFile(filename, mode='w')
    try:
        for ejfname in resultado.to_be_zipped:
            if not os.path.isfile(ejfname):
                print("\t\t->ERROR: el fichero '{0}' no existe. Para que el zip se genere, DEBES crearlo, aunque esté vacío.".format(ejfname))
        for ejfname in resultado.to_be_zipped:
            zf.write(ejfname)
        print("   ...ZIP DE ENTREGA GENERADO EN:")
        print("\n\t{0}".format(filename))
    except:
        print("...ERROR validador: No se pudo generar el zip de entrega.")
    finally:
        zf.close()

def cabecera(conf):
    msg1 = "VALIDANDO PRÁCTICA {0}".format(conf.NUM_PRACTICA)
    msg2 = "VALIDADOR v{0}".format(conf.VERSION)
    msg3 = "[ejecutándose en Python {0}.{1}.{2}]".format(version_info.major, version_info.minor, version_info.micro)
    ll = max(len(msg1),len(msg2),len(msg3))
    print("-"*ll)
    print(msg1)
    print("-"*ll)
    print(msg2)
    print(msg3)
    print("-"*ll)


def pendientes():
    while True:
        print("""Opciones:
    + Pulsa INTRO para validar todo y generar el fichero de entrega.
    + Introduce un nombre de fichero para validarlo (p.ej. ej03.py)
    + Introduce un número de fichero sin .py para validarlo con .py (p.ej. ej03 para validar ej03.py)
    + Introduce un número para validar ese ejercicio (p.ej. 3 para validar ej03.py)
    + Introduce x para salir sin hacer nada.
    """)
        opción = input("¿Qué eliges? ")
        if opción == "":
            return []
        elif opción == "x":
            sys.exit()
        else:
            if opción.startswith("ej"):
                if opción.endswith(".py"):
                    nombre = opción
                else:
                    nombre = opción + ".py"
            else:
                try:
                    n = int(opción)
                except ValueError:
                    print("Creo que has escrito mal el nombre del ejercicio, prueba otra vez")
                    continue
                nombre = "ej{:02}.py".format(n)
            if not esta_implementado(nombre):
                print ("El ejercicio {} no está implementado, prueba otra opción.".format(nombre))
            else:
                return [nombre]

def valida_uno(conf, nombre):
    print("\nProbando:")
    os.environ['__VALIDADORACTIVATED'] = 'True'
    resultado = Resultado()
    for ejercicio in conf.ejercicios:
        if ejercicio.nombre == nombre:
            prueba_ejercicio(conf, ejercicio, resultado)
            return

def valida_todos(conf):
    os.environ['__VALIDADORACTIVATED'] = 'True'
    resultado = validacion(conf)

    # Muestra la lista de ejercicios vacíos o que no existe el fichero
    num_not_implemented = len(resultado.not_implemented_exercices)
    if num_not_implemented > 0:
        num_mandatory_nie = len(resultado.not_implemented_mandatory_exercices)
        num_optional_nie = num_not_implemented - num_mandatory_nie
        print("\nEJERCICIOS NO IMPLEMENTADOS (total: {0}): ".format(num_not_implemented), end="")
        if num_mandatory_nie == 0:
            print("todos opcionales\n")
        else:
            print("{}{}\n".format(' '.join(str(f) for f in resultado.not_implemented_mandatory_exercices),
                  " (y opcionales: {})".format(num_optional_nie) if num_optional_nie > 0 else ""))

    print("<VALIDACIÓN FINALIZADA>")
    print()

    # Muestra el resultado final y, si corresponde, genera zip de entrega
    print('-'*20)
    print()
    if resultado.todas_las_obligatorias_superadas or len(resultado.not_valid_mandatory_exercices) <= conf.NUM_MAX_EJERCICIOS_MAL:
        if resultado.todas_las_pruebas_superadas:
            print("RESULTADO FINAL: VALIDACIÓN COMPLETAMENTE SUPERADA")
        elif resultado.todas_las_obligatorias_superadas:
            print("RESULTADO FINAL: VALIDACIÓN SUPERADA POR OBLIGATORIAS")
        elif len(resultado.not_valid_mandatory_exercices)==1:
            print("RESULTADO FINAL: VALIDACIÓN SUPERADA POR OBLIGATORIAS, TOLERANDO 1 ejercicio ({0}) que NO supera las pruebas".format(','.join(resultado.not_valid_mandatory_exercices)))
        else:
            print("RESULTADO FINAL: VALIDACIÓN SUPERADA POR OBLIGATORIAS, TOLERANDO {0} ejercicios ({1}) que NO superan las pruebas".format(len(resultado.not_valid_mandatory_exercices),
                                                                                                                                            ','.join(resultado.not_valid_mandatory_exercices)))
        if conf.CREATE_ZIP:
            crea_zip(conf, resultado)
    else:
        print("RESULTADO FINAL: VALIDACIÓN NO SUPERADA")
    print()
    print('-'*20)

def main():
    conf = lee_configuración()
    # lanza la validación
    cabecera(conf)
    p = pendientes()
    if p == []:
        valida_todos(conf)
    else:
        valida_uno(conf, p[0])

if __name__ == "__main__":
    if version_info < (3, 1):
        error("El validador sólo funciona sobre Python 3.1 o superior")
    main()
