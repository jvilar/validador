#!/bin/env python
'''
Created on 16/07/2014

@version 1.3.3 (2016-11-03)
@author: David Llorens (dllorens@uji.es)
         Federico Prat (fprat@uji.es)
         Juan Miguel Vilar (jvilar@uji.es)

Comprobador simple de programas
-------------------------------
Si se ejecuta en versiones con sigalrm y TimeoutError utilizará timeouts al lanzar las ejecuciones.
Esto permite que programas mal construidos (p.e. con bucles infinitos) no bloqueen al
propio comprobador.
'''

import ast
import codecs
import copy
import glob
import inspect
from io import StringIO
import os
import signal
from sys import version_info, executable
import sys
import traceback
import subprocess
import zipfile


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

def compararMatrices(expected, user):
    filasExpected, colsExpected = len(expected), len(expected[0])
    filasUser, colsUser = len(user), len(user[0])
    if filasExpected != filasUser or colsExpected != colsUser:
        return True, None
    for fila in range(len(expected)):
        for col in range(len(expected[0])):
            if expected[fila][col] != user[fila][col]:
                return ("En la fila {} y columna {} se ha encontrado el valor {} y se esperaba {}"
                         .format(fila, col, user[fila][col], expected[fila][col]))
    return None

def comprobarFichero(image, result, conf):
    try:
        with open(image) as f:
            expected = matriz(f.read())
    except:
        return "No he podido abrir el fichero de pruebas {}, comprueba que exista".format(image)
    user = result.globals["__builtins__"].get(conf.MATRIX_UJI)
    if user == None:
        return "No se ha mostrado ninguna matriz"
    return compararMatrices(expected, user)

def posDiferencia(cad1, cad2):
    if len(cad1) > len(cad2):
        cad1, cad2 = cad2, cad1
    for i in range(len(cad1)):
        if cad1[i] != cad2[i]:
            return i
    return len(cad1)

def prettyPrintDiferencias(encontrado, esperado):
    if encontrado != None and esperado != None:
        print("    Se esperaba: {0}".format(esperado))
        print("    Encontrado : {0}".format(encontrado))
        print(" "*(posDiferencia(esperado,encontrado)+15)+"**^**")
        print()
    elif esperado!= None:
        print("La salida no está completa. Faltan las siguientes líneas: ")
        print(esperado)
        print()
    else:
        print("Hay más líneas de las esperadas. Sobran las siguientes líneas: ")
        print(encontrado)
        print()

def checkOutput(filename, prueba, result, conf):
    if len(prueba.input)>0 and prueba.input[-1]=="\n":
        entrada = prueba.input[:-1].split("\n")
    else:
        entrada = prueba.input.split("\n")
    hayDiferencias, encontrado, esperado = comparaSalida(result.output, prueba.output)
    if hayDiferencias:
        print("{0} FALLO para entrada {1}.".format(filename, entrada))
        prettyPrintDiferencias(encontrado, esperado)
    ficherosDistintos = False
    if prueba.image != None:
        mensaje = comprobarFichero(prueba.image, result, conf)
        if mensaje != None:
            print("{} FALLO para entrada {}. {}".format(filename, entrada, mensaje))
            ficherosDistintos = True
    return not (hayDiferencias or ficherosDistintos)

def do_test(filename, em, prueba, conf):
    if prueba.functions != None:
        isOk = check_functions(filename, prueba, conf, em)
        if not isOk:
            return False
    result = em.exec_program(prueba.input)
    if result.exception != None:
        if not conf.TIMEOUT is None and isinstance (result.exception, TimeoutError):
            print("{0} TIMEOUT para entrada {1}.".format(filename, prueba.input.split()))
        else:
            print("{0} FALLO para entrada {1}. Lanzada excepción:".format(filename, prueba.input.split()))
            print(result.error)
        return False
    if result.error != "":
        print("{0} FALLO para entrada {1}. Salida de error:".format(filename, prueba.input.split()))
        print(result.error)
        return False
    return checkOutput(filename, prueba, result, conf)

def redirectIO (input, output, error):
    stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = input, output, error
    return (stdin, stdout, stderr)

def restoreIO (io):
    sys.stdin.close()
    sys.stdout.close()
    sys.stderr.close()
    sys.stdin, sys.stdout, sys.stderr = io

class timeout:
    def __init__(self, seconds=1, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        if not self.seconds is None:
            signal.signal(signal.SIGALRM, self.handle_timeout)
            signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        if not self.seconds is None:
            signal.alarm(0)

class executionResult:
    def __init__(self, value = None, output = None, error = None, exception = None, globals = None):
        self.value = value
        self.output = output
        self.error = error
        self.exception = exception
        self.globals = globals

class executionManager:
    def __init__(self, filename, timeout = None):
        self.timeout = timeout
        source = open(filename, encoding="utf-8").read()
        self.filename = filename
        self.prg = compile(source, filename, "exec")
        tree = ast.parse(source, filename, "exec")
        decls = [ node for node in tree.body if node.__class__.__name__
                    in [ "FunctionDef", "ImportFrom", "Import", "ClassDef", "AsyncFunctionDef"] ]
        declarations = compile(ast.Module(body = decls, lineno = 0, col_offset = 0), filename, "exec")
        self.functions = {}
        result = self._do_exec(exec, (declarations, self.functions), "sd")

    def exec_program(self, input):
        globals = {}
        result = self._do_exec(exec, (self.prg, globals), input)
        result.globals = globals
        return result

    def exists_function(self, fname):
        return fname in self.functions

    def exec_function(self, fname, pars, input):
        f = self.functions[fname]
        result = self._do_exec(f, pars, input)
        result.globals = self.functions
        return result

    def _do_exec(self, f, pars, input):
        output = StringIO("")
        error = StringIO("")
        io = redirectIO(StringIO(input), output, error)
        exception = None
        value = None
        try:
            with timeout(self.timeout):
                value = f(*pars)
        except Exception as e:
            exception = e
            lines = traceback.format_exception(*sys.exc_info())
            i = 0
            while i < len(lines):
                l = lines[i]
                if 'validador.py' not in l:
                    error.write(l)
                i += 1
        finally:
            result = executionResult(value = value, output = output.getvalue(), error = error.getvalue(), exception = exception)
            restoreIO(io)
        return result

def check_functions(filename, prueba, conf, em):
    original = {}
    for k, v in em.functions.items():
        if k != "__builtins__":
            original[k] = copy.deepcopy(v)
        else:
            original[k] = v

    for pf in prueba.functions:
        if not em.exists_function(pf.fname):
            print ("{} FALLO, no implementa la función {}.".format(filename, pf.fname))
            return False
        for test in pf.tests:
            if not is_ok_function(pf.fname, test, filename, em, original):
                return False
    return True

def is_ok_function(fname, test, filename, em, original):
    parsActual = copy.deepcopy(test.pars)
    result = em.exec_function(fname, parsActual, test.stdin)
    if result.exception != None:
        print ("{} FALLO, la función {} con {} lanza una excepción:".format(filename, fname, test.pars))
        print (result.error)
        return False
    if result.value != test.result:
        print ("{} FALLO, la función {} con {} da como resultado {} en lugar de {}".format(filename, fname, test.pars, result.value, test.result))
        return False
    for (var, valor) in result.globals.items():
        if var not in original or valor != original[var]:
            print ("{} FALLO, la función {} asigna a la variable global {}.".format(filename, fname, var))
            return False
    if test.finalPars != parsActual:
        print ("{} FALLO, la función {} no trata los parametros como se espera.".format(filename, fname))
        for i,p in enumerate(test.finalPars):
            if p != parsActual[i]:
                print("Al salir, el parámetro {} tenía que valer {} y vale {}".format(i + 1, p, parsActual[i]))
        return False
    hayDiferencias, encontrado, esperado = comparaSalida(result.output, test.stdout)
    if hayDiferencias:
        print("{} FALLO, la funcion {} con {} no da la salida correcta.".format(filename, fname, test.pars))
        prettyPrintDiferencias(encontrado, esperado)
        return False
    return True

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
    em = executionManager(filename, conf.TIMEOUT)
    for prueba in ejercicio.pruebas:
        isOk = do_test(filename, em, prueba, conf)
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
    fields = [("VERSION", "1.3.3"),
              ("TIMEOUT", 5), #seconds
              ("ENVIRONMENT_FLAG", "__MATRIX_GLOBAL__"),
              ("MATRIX_UJI", "__uji_matrix"),
              ("NUM_PRACTICA", -1),
              ("work", []),
              ("CREATE_ZIP", True),
              ("NUM_MAX_EJERCICIOS_MAL", 0) # de los obligatorios
              ]

    def __init__(self, variables):
        self.variables = variables
        for (nombre, valor) in Configuración.fields:
            self.asigna(nombre, valor)
        try:
            _ = signal.SIGALRM
            _ = TimeoutError
        except:
            self.TIMEOUT = None

    def asigna(self, nombre, valor):
        v = self.variables.get(nombre, valor)
        if nombre != "work":
            setattr(self, nombre, v)
        else:
            self.ejercicios = [ Ejercicio(e, n) for n, e in enumerate(v) ]


def has_len_and_items(what, description):
    if not hasattr(what, "__getitem__"):
        error(description + " no es del tipo adecuado, no tiene __getitem__")
    if not hasattr(what, "__len__"):
        error(description + " no es del tipo adecuado, no tiene __len__")

def is_string(what, description):
    if not isinstance(what, str):
        error(description + " no es una cadena")

def is_iterable(what, description):
    if not hasattr(what, "__iter__"):
        error(description + " no es iterable")

def at_most_len(what, description, maxlen):
    if len(what) > maxlen:
        error("{} debería tener como máximo {} ítems".format(description, maxlen))

def at_least_len(what, description, minlen):
    if len(what) < minlen:
        print (what)
        error("{} debería tener como mínimo {} ítems".format(description, minlen))

def exact_len(what, description, expected_len):
    if len(what) != expected_len:
        error("{} debería tener {} ítems".format(description, expected_len))

class Ejercicio:
    def __init__(self, entrada, n):
        desc = "la entrada {} de la lista work".format(n)
        has_len_and_items(entrada, desc)
        try:
            self.nombre = entrada[0]
        except:
            error("No puedo leer el primer elemento de {}".format(desc))
        self.pruebas = [Prueba(p, self.nombre, i) for i, p in enumerate(entrada[-1])]
        self.obligatorio = len(entrada) == 2 or entrada[1]

class Prueba:
    def __init__(self, entrada, pname, i):
        desc = "la prueba {} del programa {}".format(i, pname)
        has_len_and_items(entrada, desc)
        at_least_len(entrada, desc, 2)
        at_most_len(entrada, desc, 4)

        is_string(entrada[0], "la entrada de " + desc)
        self.input = entrada[0]
        is_string(entrada[1], "la salida de " + desc)
        self.output = entrada[1]
        if len(entrada) > 2 and not entrada[2] is None:
            is_string(entrada[2], "la imagen de " + desc)
        self.image = entrada[2] if len(entrada) > 2 else None
        if len(entrada) > 3:
            is_iterable(entrada[3], "las pruebas de función de " + desc)
        self.functions = [ FunctionTestList(ftl, pname, j) for j, ftl in enumerate(entrada[3]) ] if len(entrada) > 3 else None

class FunctionTestList:
    def __init__(self, entrada, pname, j):
        desc = "la prueba {} de función del programa {}".format(j, pname)
        has_len_and_items(entrada, desc)
        exact_len(entrada, desc, 2)
        self.fname = entrada[0]
        self.tests = [ FunctionTest(ft, pname, self.fname, i) for i, ft in enumerate(entrada[1]) ]

class FunctionTest:
    def __init__(self, entrada, pname, fname, i):
        desc = "la prueba {} de la función {} del programa {}".format(i, fname, pname)
        has_len_and_items(entrada, desc)
        exact_len(entrada, desc, 5)
        self.pars = entrada[0]
        self.stdin = entrada[1]
        self.result = entrada[2]
        self.finalPars = entrada[3]
        self.stdout = entrada[4]

def lee_configuración():
    # busca el fichero de configuración del validador
    matching_files = glob.glob('./validador_prac[0-9]*.cfg')
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


def opciones():
    while True:
        print("""Opciones:
    + Pulsa INTRO para validar todo y generar el fichero de entrega.
    + Introduce un nombre de fichero para validarlo (p.ej. ej03.py)
    + Introduce un número de fichero sin .py para validarlo con .py (p.ej. ej03 para validar ej03.py)
    + Introduce un número para validar ese ejercicio (p.ej. 3 para validar ej03.py)
    + Introduce g para generar los ficheros vacíos que falten.
    + Introduce x para salir sin hacer nada.
    """)
        opción = input("¿Qué eliges? ")
        if opción == "":
            return []
        elif opción == "x":
            sys.exit()
        elif opción == "g":
            return opción
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

def genera_ficheros(conf):
    for ejercicio in conf.ejercicios:
        if not os.path.isfile(ejercicio.nombre):
            open(ejercicio.nombre, "w").close()

def valida_uno(conf, nombre):
    print("\nProbando:")
    os.environ[conf.ENVIRONMENT_FLAG] = 'TRUE'
    resultado = Resultado()
    for ejercicio in conf.ejercicios:
        if ejercicio.nombre == nombre:
            prueba_ejercicio(conf, ejercicio, resultado)
            return

def valida_todos(conf):
    os.environ[conf.ENVIRONMENT_FLAG] = 'TRUE'
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
    op = opciones()
    if op == "g":
        genera_ficheros(conf)
    elif op == []:
        valida_todos(conf)
    else:
        valida_uno(conf, op[0])

if __name__ == "__main__":
    if version_info < (3, 1):
        error("El validador sólo funciona sobre Python 3.1 o superior")
    main()
