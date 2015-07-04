#!/usr/bin/env python3

import argparse, os, sys, subprocess

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start C-Reduce for OpenCL kernel.')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--platform', '-p', help='Platform under test')
    parser.add_argument('--device', '-d', help='Device under test')
    parser.add_argument('--cl-launcher', help='Path to cl_launcher application')
    parser.add_argument('--clang', help='Path to clang application')
    parser.add_argument('--libclc', help='Path to libclc include directory')
    if sys.platform == 'win32':
        parser.add_argument('--oclgrind-platform', help='Platform for Oclgrind')
        parser.add_argument('--oclgrind-device', help='Device for Oclgrind')
    parser.add_argument('test', nargs=1, help='Test script')
    parser.add_argument('kernel', nargs=1, help='OpenCL kernel')

    args = parser.parse_args()

    env = os.environ

    if not args.platform:
        if not env.get('CREDUCE_TEST_PLATFORM'):
            parser.error('No platform specified and CREDUCE_TEST_PLATFORM not defined!')
    else:
        env['CREDUCE_TEST_PLATFORM'] = args.platform

    if not args.device:
        if not env.get('CREDUCE_TEST_DEVICE'):
            parser.error('No device specified and CREDUCE_TEST_DEVICE not defined!')
    else:
        env['CREDUCE_TEST_DEVICE'] = args.device

    if not args.cl_launcher:
        if not env.get('CREDUCE_TEST_CLLAUNCHER'):
            parser.error('No cl-launcher specified and CREDUCE_TEST_CLLAUNCHER not defined!')
    else:
        env['CREDUCE_TEST_CLLAUNCHER'] = os.path.abspath(args.cl_launcher)

    if args.clang:
        env['CREDUCE_TEST_CLANG'] = os.path.abspath(args.clang)

    if not args.libclc:
        if not env.get('CREDUCE_TEST_LIBCLC_INCLUDE_PATH'):
            parser.error('No libclc specified and CREDUCE_TEST_LIBCLC_INCLUDE_PATH not defined!')
    else:
        env['CREDUCE_TEST_LIBCLC_INCLUDE_PATH'] = os.path.abspath(args.libclc)

    if sys.platform == 'win32':
        if not args.oclgrind_platform:
            if not env.get('CREDUCE_TEST_OCLGRIND_PLATFORM'):
                parser.error('No oclgrind-platform specified and CREDUCE_TEST_OCLGRIND_PLATFORM not defined!')
        else:
            env['CREDUCE_TEST_OCLGRIND_PLATFORM'] = args.oclgrind_platform

        if not args.oclgrind_device:
            if not env.get('CREDUCE_TEST_OCLGRIND_DEVICE'):
                parser.error('No oclgrind-device specified and CREDUCE_TEST_OCLGRIND_DEVICE not defined!')
        else:
            env['CREDUCE_TEST_OCLGRIND_DEVICE'] = args.oclgrind_device

    if sys.platform == 'win32':
        creduceArgs = ['perl', '--', 'creduce.pl']
    else:
        creduceArgs = ['creduce']

    creduceArgs.extend(['-n', '1'])

    if args.verbose:
        creduceArgs.append('--verbose')

    creduceArgs.extend(args.test)
    creduceArgs.extend(args.kernel)

    subprocess.call(creduceArgs, env=env, universal_newlines=True)
