import sys
import pyvisa
import numpy as np
import time
import csv
import matplotlib.pyplot as plt
#from instrumental.drivers.sourcemeasureunit.keithley import Keithley_2400
from pint import Quantity as Q_
from utils import *

USB_adress_COUNTER = 'USB0::0x0957::0x1807::MY50009613::INSTR'
USB_adress_SOURCEMETER = 'USB0::0x0957::0x8C18::MY51141236::INSTR'

if length(sys.argv)>1:
	Die = sys.argv[1]
else:
	Die = ''

Vbd = 24.2 # [V]
max_overbias = 10 # [%]
step_overbias = 1 # [%] Each step 1% more overbias


# Frequency measurements settings
slope = 'NEG' # Positive('POS')/ Negative('NEG') slope trigger
delta_thres = 0.0025 # Resolution of threshold trigger is 2.5 mV


def open_SourceMeter():
    SOURCEMETER = rm.open_resource(USB_adress_SOURCEMETER)
    SOURCEMETER.write('*RST') # Reset to default settings
    SOURCEMETER.write(':SOUR1:FUNC:MODE VOLT')
    SOURCEMETER.write(':SENS1:CURR:PROT 100E-06') # Set compliance at 100 uA

    return SOURCEMETER

# Open Frequency Counter and set it to count measurement
def open_FreqCounter():
	COUNTER = rm.open_resource(USB_adress_COUNTER)

	COUNTER.write('*RST') # Reset to default settings

	COUNTER.write('CONF:TOT:TIM 1') # Collect the number of events in 1 sec

	COUNTER.write('INP1:COUP DC') # DC coupled
	COUNTER.write('INP1:IMP 50') # 50 ohm imput impedance
	COUNTER.write('INP1:SLOP {}'.format(slope)) # Set slope trigger
	COUNTER.timeout = 600000 # Timeout of 60000 msec
	time.sleep(1)

	return COUNTER

def bring_to_breakdown(SOURCEMETER, Vbd):
    Vinit = 0
    Vstep = 0.25

    while (Vinit < Vbd):
        SOURCEMETER.write(':SOUR1:VOLT {}'.format(Vinit))
        SOURCEMETER.write(':OUTP ON')
        #SOURCEMETER.set_voltage(Q_(Vinit, 'V'))
        Vinit = Vinit + Vstep
        time.sleep(0.25)

    SOURCEMETER.write(':SOUR1:VOLT {}'.format(Vbd))
	SOURCEMETER.write(':OUTP ON')

	print('Sourcemeter at breakdown: {} V'.format(Vbd))



def bring_down_from_breakdown(SOURCEMETER, Vcurrent):
    Vstep = 0.25
    Vcurrent = Vcurrent - Vstep

    while (Vcurrent > 0):
        SOURCEMETER.write(':SOUR1:VOLT {}'.format(Vcurrent))
        SOURCEMETER.write(':OUTP ON')
        #SOURCEMETER.set_voltage(Q_(Vinit, 'V'))
        Vinit = Vinit - Vstep
        time.sleep(0.25)

    SOURCEMETER.write(':SOUR1:VOLT 0')
	SOURCEMETER.write(':OUTP ON')
    print('Sourcemeter at 0 V')


# Set bias at Vbias and collect counts during 1 sec
def take_measure(COUNTER, SOURCEMETER, Vbias, Vthres):
    # Set voltage to Vbias
    SOURCEMETER.write(':SOUR1:VOLT {}'.format(Vbias))
    SOURCEMETER.write(':OUTP ON')
    SOURCEMETER.set_voltage(Q_(Vbias, 'V'))
    time.sleep(0.5)

    # Initiate couting
	COUNTER.write('INP1:LEV {}'.format(Vthres)) # Set threshold
    COUNTER.write('INIT') # Initiate couting
    COUNTER.write('*WAI')
    num_counts = COUNTER.query_ascii_values('FETC?')
    return num_counts[0]



def sweep_threshold(COUNTER, SOURCEMETER, Vbias):
	Vthresh = delta_thres
	counts = [take_measure(COUNTER, SOURCEMETER, Vbias, -Vthresh)]

	while (counts[-1] != 0):
		Vthresh = Vthresh + delta_thres
		counts = np.append(counts, take_measure(COUNTER, SOURCEMETER, Vbias, -Vthresh))

	return [Vthresh, counts]



def meas_laser_counts(COUNTER, SOURCEMETER, Vbias, limit_thres):
	num_thres = int(limit_thres / delta_thres)
	counts = np.empty(num_thres)

	for i in range (0:num_thres):
		counts[i] = take_measure(COUNTER, SOURCEMETER, Vbias, -(i + 1)*delta_thres)

	return counts




rm = pyvisa.ResourceManager()
COUNTER = open_FreqCounter()
SOURCEMETER = open_SourceMeter()

bring_to_breakdown(SOURCEMETER, Vbd)

num_measures = int(max_overbias/step_overbias) + 1 # 0% and max_overbias% included
vec_overbias = Vbd + Vbd/100 * np.linspace(0, max_overbias, num = num_measures)
dark_counts = np.empty(num_measures)
max_threshold = np.empty(num_measures) # Max threshold to measure counts (peak's height)

print('Performing Dark counts measurement...')

for i in range (0, num_measures):
	result = sweep_threshold(COUNTER, SOURCEMETER, vec_overbias[i])
	max_threshold[i] = result[0]
    dark_counts[i] = result[1]

print('Dark counts measurement finished...')



input("Press Enter once laser is on...")



print('Performing Laser counts measurement...')
laser_counts = np.empty(num_measures)

for i in range (0, num_measures):
	dark_counts[i] = meas_laser_counts(COUNTER, SOURCEMETER, vec_overbias[i], max_threshold[i])

print('Laser counts measurement finished...')

bring_down_from_breakdown(SOURCEMETER, vec_overbias[-1])

# Now SPAD is at 0 V, take QE measurements
# Save data

plt.figure()
plt.plot(voltage_counts[1], voltage_counts[2], 'ro')
plt.title('Dark counts')
plt.xlabel('Reverse Bias Voltage [V]')
plt.ylabel('Dark counts [1/s]')
plt.grid(True)
plt.savefig("{}-dark_counts_vs_overbias_Vbd_{}_{}max_{}step.png".format(Die, Vbd.magnitude, max_overbias, step_overbias))

with open("{}-dark_counts_vs_overbias_Vbd_{}_{}max_{}step.csv".format(Die, Vbd.magnitude, max_overbias, step_overbias), "w", newline="") as file:
    writer = csv.writer(file, dialect='excel')
    writer.writerows(map(lambda x: [x], voltage_counts[2]))


COUNTER.close()
SOURCEMETER.close()
