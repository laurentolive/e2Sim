// e2Sim - CI: runner self-tests and fan example campaign on both architectures.
// Agent: Windows with GNU make, MSYS2 (mingw32 + ucrt64 gcc/gdb), Python 3.10+ (pyyaml, pytest)
// and an e2sim_toolchains.yaml (E2SIM_TOOLCHAINS or ~/.e2sim/). Licence: E2SIM_LICENSE_KEY (credential).
pipeline {
    agent { label 'windows' }
    environment {
        E2SIM_LICENSE_KEY = credentials('e2sim-license-key')
    }
    stages {
        stage('Build') {
            steps {
                dir('selftest/blink') {
                    bat 'make TOOLCHAIN=host32 && make TOOLCHAIN=host64'
                }
                dir('examples/fan') {
                    bat 'make TOOLCHAIN=host32 && make TOOLCHAIN=host64'
                }
            }
        }
        stage('Runner self-tests') {
            steps {
                dir('selftest') {
                    bat 'python -m pytest -q --junitxml=out/selftest32.xml --e2sim-toolchain host32 .'
                    bat 'python -m pytest -q --junitxml=out/selftest64.xml --e2sim-toolchain host64 .'
                }
            }
        }
        stage('Coverage') {
            steps {
                dir('examples/fan') {
                    bat 'make coverage TOOLCHAIN=host32 PYTEST_OPTS="-q"'
                }
            }
        }
        stage('Fan example') {
            steps {
                dir('examples/fan') {
                    bat 'python -m pytest tests -q --e2sim-toolchain host32 --junitxml=out/fan32.xml --e2sim-record out/rec32'
                    bat 'python -m pytest tests -q --e2sim-toolchain host64 --junitxml=out/fan64.xml'
                }
            }
        }
    }
    post {
        always {
            junit 'selftest/out/*.xml, examples/fan/out/*.xml'
            archiveArtifacts artifacts: 'examples/fan/out/rec32/*.e2simrec, examples/fan/tests/ref/*.actual.png, examples/fan/out/coverage/**', allowEmptyArchive: true
        }
    }
}
