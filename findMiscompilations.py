#!/usr/bin/env python3

import argparse, tempfile, os, sys, subprocess, shutil
import openCLTest
import reduceDimension

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optionally generate, run and compare OpenCL kernels.')
    inputGroup = parser.add_mutually_exclusive_group(required=True)
    inputGroup.add_argument('--generate', type=int, metavar='N', help='Generate N kernels on the fly')
    inputGroup.add_argument('--kernel-dir', dest='kernelDir', help='OpenCL kernel directory')
    inputGroup.add_argument('--kernels', metavar='KERNEL', nargs='+', help='OpenCL kernels')
    processGroup = parser.add_mutually_exclusive_group()
    processGroup.add_argument('--preprocess', action='store_true', help='Preprocess kernels')
    processGroup.add_argument('--preprocessed', action='store_true', help='Kernels are already preprocessed')
    parser.add_argument('--reduce-dimension', dest='reduceDimension', action='store_true', help='Reduce dimensions of the kernels')
    parser.add_argument('--stop-after', dest='stopAfter', choices=['generate', 'preprocess', 'check', 'dimension'], help='When to stop')
    parser.add_argument('--output', help='Output directory')

    args = parser.parse_args()
    timeLimit = 300

    if args.generate or args.preprocess or not args.preprocessed:
        clSmithPath = os.environ.get('CLSMITH_PATH')
        if not clSmithPath:
            print('CLSMITH_PATH not defined!')
            sys.exit(1)

    if args.stopAfter != 'generate':
        testPlatform = os.environ.get('CREDUCE_TEST_PLATFORM')
        if not testPlatform:
            print('CREDUCE_TEST_PLATFORM not defined!')
            sys.exit(1)

        testDevice = os.environ.get('CREDUCE_TEST_DEVICE')
        if not testDevice:
            print('CREDUCE_TEST_DEVICE not defined!')
            sys.exit(1)

        clLauncher = os.environ.get('CREDUCE_TEST_CLLAUNCHER')
        if not clLauncher:
            print('CREDUCE_TEST_CLLAUNCHER not defined!')
            sys.exit(1)

        clang = os.environ.get('CREDUCE_TEST_CLANG', 'clang')

        openclIncludePath = os.environ.get('CREDUCE_OPENCL_INCLUDE_PATH')
        if not openclIncludePath:
            print('CREDUCE_OPENCL_INCLUDE_PATH not defined!')
            sys.exit(1)

        if sys.platform == 'win32':
            openCLEnv = openCLTest.WinOpenCLEnv(clLauncher, clang, openclIncludePath, 0, 0)
        else:
            openCLEnv = openCLTest.UnixOpenCLEnv(clLauncher, clang, openclIncludePath)

    origDir = os.getcwd()

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

    if not args.output:
        outputDir = tempfile.mkdtemp(prefix='kernels.', dir='.')
    else:
        outputDir = args.output

    if not os.path.exists(outputDir):
        os.mkdir(outputDir)

    os.chdir(outputDir)

    if not args.preprocess and not args.preprocessed:
        shutil.copy(os.path.join(clSmithPath, 'CLSmith.h'), '.')
        shutil.copy(os.path.join(clSmithPath, 'safe_math_macros.h'), '.')
        shutil.copy(os.path.join(clSmithPath, 'cl_safe_math_macros.h'), '.')

    for inputKernel in inputKernels:
        kernelFile = inputKernel
        kernelName = os.path.basename(kernelFile)

        print(kernelName, end=' ', flush=True)

        if args.generate:
            try:
                openCLEnv.check_output([clSmithTool], timeLimit)
            except subprocess.SubprocessError:
                print('-> aborted generation')
                continue

            os.rename('CLProg.c', kernelFile)
            print('-> generated', end=' ', flush=True)

        if args.stopAfter == 'generate':
            continue

        if args.preprocess:
            try:
                openCLEnv.check_output([clang, '-I', clSmithPath, '-E', '-CC', '-o', '_' + kernelName, kernelFile], timeLimit)
                os.rename('_' + kernelName, kernelName)
                kernelFile = kernelName
                print('-> preprocessed', end=' ', flush=True)
            except subprocess.SubprocessError:
                print('-> aborted preprocessing')
                continue
        else:
            if os.path.abspath(outputDir) != origDir:
                shutil.copy(kernelFile, kernelName)
                kernelFile = kernelName

        if args.stopAfter == 'preprocess':
            continue

        outputOptimised = openCLEnv.runKernel(testPlatform, testDevice, kernelFile, timeLimit)
        if not outputOptimised:
            print('-> aborted optimised')
            continue

        outputUnoptimised = openCLEnv.runKernel(testPlatform, testDevice, kernelFile, timeLimit, optimised=False)
        if not outputUnoptimised:
            print('-> aborted unoptimised')
            continue

        if outputOptimised == outputUnoptimised:
            print('-> correct')
            continue
        else:
            print('-> miscompiled', end=' ', flush=True)

        if args.stopAfter == 'check':
            continue

        if args.reduceDimension:
            kernelTest = openCLTest.InterestingnessTest(openCLEnv, kernelFile, testPlatform, testDevice)
            dimReducer = reduceDimension.DimensionReducer(kernelFile, kernelTest)
            result = dimReducer.reduce()

            if not result:
                print('-> aborted dimension')
                continue
            else:
                print('-> dimension reduced', end=' ', flush=True)

        #if args.stopAfter == 'dimension':
        #continue

        print('-> done')

    os.chdir(origDir)
