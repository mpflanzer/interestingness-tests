#!/usr/bin/env python3

import argparse, tempfile, os, sys, subprocess, shutil, fileinput, re
import openCLTest
from openCLTest import *
import reduceDimension

def which(cmd):
    if sys.platform == 'win32' and '.' not in cmd:
        cmd += '.exe'

    if os.access(cmd, os.F_OK):
        return cmd

    for path in os.environ["PATH"].split(os.pathsep):
        if os.access(os.path.join(path, cmd), os.F_OK):
            return os.path.join(path, cmd)

    return None

def removePreprocessorComments(kernelName):
    for line in fileinput.input(kernelName, inplace=True):
        if re.match('^# \d+ "[^"]*"', line):
            continue

        print(line, end='')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optionally generate, run and compare OpenCL kernels.')
    inputGroup = parser.add_mutually_exclusive_group(required=True)
    inputGroup.add_argument('--generate', type=int, metavar='N', help='Generate N kernels on the fly')
    inputGroup.add_argument('--kernel-dir', dest='kernelDir', help='OpenCL kernel directory')
    inputGroup.add_argument('--kernels', metavar='KERNEL', nargs='+', help='OpenCL kernels')
    processGroup = parser.add_mutually_exclusive_group()
    processGroup.add_argument('--preprocess', action='store_true', help='Preprocess kernels')
    processGroup.add_argument('--preprocessed', action='store_true', help='Kernels are already preprocessed')
    parser.add_argument('--check', action='store_true', help='Check whether the kernel is interesting')
    reduceGroup = parser.add_mutually_exclusive_group()
    reduceGroup.add_argument('--reduce-dimension', dest='reduceDimension', action='store_const', const=1, help='Reduce dimensions of the kernels')
    reduceGroup.add_argument('--reduce-dimension-unchecked', dest='reduceDimension', action='store_const', const=2, help='Reduce dimensions of the kernels (unchecked)')
    parser.add_argument('--reduce', action='store_true', help='Start reduction of the kernels')
    parser.add_argument('--test', action='store', choices=InterestingnessTest.availableTests, default='miscompiled', help='Criterion which the kernel has to fulfill')
    parser.add_argument('--output', help='Output directory')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()
    timeLimit = 300

    if args.generate or args.preprocess or not args.preprocessed:
        clSmithPath = os.environ.get('CLSMITH_PATH')
        if not clSmithPath:
            print('CLSMITH_PATH not defined!')
            sys.exit(1)

    if (args.check and args.test != 'valid') or args.reduceDimension == 1 or args.reduce:
        testPlatform = os.environ.get('CREDUCE_TEST_PLATFORM')
        if not testPlatform:
            print('CREDUCE_TEST_PLATFORM not defined!')
            sys.exit(1)

        testDevice = os.environ.get('CREDUCE_TEST_DEVICE')
        if not testDevice:
            print('CREDUCE_TEST_DEVICE not defined!')
            sys.exit(1)
    else:
        testPlatform = None
        testDevice = None

    if args.check or args.reduceDimension == 1 or args.reduce:
        clLauncher = os.environ.get('CREDUCE_TEST_CLLAUNCHER', os.path.abspath('./cl_launcher'))
        if not which(clLauncher):
            clLauncher = os.path.basename(clLauncher)

            if not which(clLauncher):
                print('CREDUCE_TEST_CLLAUNCHER not defined and cl_launcher not found!')
                sys.exit(1)
    else:
        clLauncher = None

    clang = os.environ.get('CREDUCE_TEST_CLANG', os.path.abspath('./clang'))
    if not which(clang):
        clang = os.path.basename(clang)

        if not which(clang):
            print('CREDUCE_TEST_CLANG not defined and clang not found!')
            sys.exit(1)

    libclcIncludePath = os.environ.get('CREDUCE_LIBCLC_INCLUDE_PATH')

    if args.reduce:
        env = os.environ

        env['CREDUCE_TEST_PLATFORM'] = testPlatform
        env['CREDUCE_TEST_DEVICE'] = testDevice
        env['CREDUCE_TEST_CLLAUNCHER'] = clLauncher
        env['CREDUCE_TEST_CLANG'] = clang
        env['CREDUCE_LIBCLC_INCLUDE_PATH'] = libclcIncludePath

        if sys.platform == 'win32':
            if not env.get('CREDUCE_TEST_OCLGRIND_PLATFORM'):
                die('No oclgrind-platform specified and CREDUCE_TEST_OCLGRIND_PLATFORM not defined!')

            if not env.get('CREDUCE_TEST_OCLGRIND_DEVICE'):
                die('No oclgrind-device specified and CREDUCE_TEST_OCLGRIND_DEVICE not defined!')

            testPlatformOclgrind = int(env.get('CREDUCE_TEST_OCLGRIND_PLATFORM'))
            testDeviceOclgrind = int(env.get('CREDUCE_TEST_OCLGRIND_DEVICE'))
    else:
        testPlatformOclgrind = 0
        testDeviceOclgrind = 0

    if sys.platform == 'win32':
        openCLEnv = WinOpenCLEnv(clLauncher, clang, libclcIncludePath, testPlatformOclgrind, testDeviceOclgrind)
    else:
        openCLEnv = UnixOpenCLEnv(clLauncher, clang, libclcIncludePath)

    origDir = os.getcwd()

    # Get kernel filenames
    if args.generate:
        inputKernels = ['CLProg_%d.cl' % i for i in range(0, args.generate)]
        countKernels = args.generate
        clSmithTool = os.path.join(clSmithPath, 'CLSmith')
    elif args.kernels:
        inputKernels = [os.path.join(origDir, inputKernel) for inputKernel in args.kernels]
        countKernels = len(inputKernels)
    elif args.kernelDir:
        kernelDir = os.path.join(origDir, args.kernelDir)
        inputKernels = [os.path.join(kernelDir, inputKernel) for inputKernel in os.listdir(kernelDir) if os.path.isfile(os.path.join(kernelDir, inputKernel))]
        countKernels = len(inputKernels)

    # Create output directory
    if not args.output:
        outputDir = tempfile.mkdtemp(prefix='kernels.', dir='.')
    else:
        outputDir = args.output

    if not os.path.exists(outputDir):
        os.mkdir(outputDir)

    os.chdir(outputDir)

    # Create test file
    if args.reduce:
        if sys.platform == 'win32':
            pass
        else:
            testFileName = 'test_wrapper.sh'
            testFile = open(testFileName, 'w')
            testFile.write('#!/bin/bash\n')
            testFile.write(os.path.abspath(openCLTest.__file__) + ' --test ' + args.test + ' $1\n')
            testFile.close()
            os.chmod(testFileName, 0o744)

    # Copy header files if unpreprocessed kernels should be reduced etc.
    if not args.preprocess and not args.preprocessed:
        shutil.copy(os.path.join(clSmithPath, 'CLSmith.h'), '.')
        shutil.copy(os.path.join(clSmithPath, 'safe_math_macros.h'), '.')
        shutil.copy(os.path.join(clSmithPath, 'cl_safe_math_macros.h'), '.')

    # Iterate over all kernels
    for inputKernel in inputKernels:
        kernelFile = inputKernel
        kernelName = os.path.basename(kernelFile)

        print('')
        print(kernelName, end=' ', flush=True)

        # Generate kernel if desired
        if args.generate:
            try:
                openCLEnv.check_output([clSmithTool], timeLimit)
            except subprocess.SubprocessError:
                print('-> aborted generation')
                continue

            os.rename('CLProg.c', kernelFile)

            if args.verbose:
                print('-> generated', end=' ', flush=True)

        # Preprocess kernel if desired or copy original kernel
        if args.preprocess:
            try:
                openCLEnv.check_output([clang, '-I', clSmithPath, '-E', '-CC', '-o', '_' + kernelName, kernelFile], timeLimit)
                removePreprocessorComments('_' + kernelName)
                os.rename('_' + kernelName, kernelName)
                kernelFile = kernelName

                if args.verbose:
                    print('-> preprocessed', end=' ', flush=True)
            except subprocess.SubprocessError:
                print('-> aborted preprocessing', end=' ', flush=True)
                continue
        else:
            if os.path.abspath(outputDir) != origDir:
                shutil.copy(kernelFile, kernelName)
                kernelFile = kernelName

        # Check if kernel is interesting
        if args.check:
            kernelTest = InterestingnessTest(args.test, openCLEnv, kernelFile, testPlatform, testDevice)
            result = kernelTest.runTest()

            if not result:
                print('-> check failed', end=' ', flush=True)
                continue
            else:
                if args.verbose:
                    print('-> check succeeded', end=' ', flush=True)

        # Reduce dimension of the kernel
        if args.reduceDimension:
            kernelTest = InterestingnessTest(args.test, openCLEnv, kernelFile, testPlatform, testDevice)
            dimReducer = reduceDimension.DimensionReducer(kernelFile, kernelTest)
            result = dimReducer.reduce(args.reduceDimension == 2)

            if not result:
                if args.verbose:
                    print('-> dimension unchanged', end=' ', flush=True)
            else:
                if args.verbose:
                    print('-> dimension reduced', end=' ', flush=True)

        if args.reduce:
            if sys.platform == 'win32':
                creduceArgs = ['perl', '--', which('creduce.pl')]
            else:
                creduceArgs = ['creduce']

            creduceArgs.extend(['-n', '1'])

            if args.verbose:
                creduceArgs.append('--verbose')

            creduceArgs.append(testFileName)
            creduceArgs.append(kernelFile)

            subprocess.call(creduceArgs, env=env, universal_newlines=True)

        print('-> done', end=' ', flush=True)

    os.chdir(origDir)
    print('')
