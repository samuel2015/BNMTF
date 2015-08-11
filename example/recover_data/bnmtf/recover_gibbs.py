"""
Recover the toy dataset generated by example/generate_toy/bnmtf/generate_bnmtf.py
We use the parameters for the true priors.

We can plot the values Fik, Skl, Gjl, or tau, to see how the Gibbs sampler converges. 
"""

project_location = "/home/tab43/Documents/Projects/libraries/"
import sys
sys.path.append(project_location)

from BNMTF.code.bnmtf_gibbs import bnmtf_gibbs
from ml_helpers.code.mask import calc_inverse_M

import numpy, matplotlib.pyplot as plt

##########

input_folder = project_location+"BNMTF/example/generate_toy/bnmtf/"

iterations = 1000
init = 'random'
I, J, K, L = 100, 50, 10, 5

alpha, beta = 10., 1.
lambdaF = numpy.ones((I,K))
lambdaS = numpy.ones((K,L)) 
lambdaG = numpy.ones((J,L)) 
priors = { 'alpha':alpha, 'beta':beta, 'lambdaF':lambdaF, 'lambdaS':lambdaS, 'lambdaG':lambdaG }

# Load in data
R = numpy.loadtxt(input_folder+"R.txt")
M = numpy.loadtxt(input_folder+"M.txt")
M_test = calc_inverse_M(M)

# Run the Gibbs sampler
BNMTF = bnmtf_gibbs(R,M,K,L,priors)
BNMTF.initialise(init)
BNMTF.run(iterations)

taus = BNMTF.all_tau
Fs = BNMTF.all_F
Ss = BNMTF.all_S
Gs = BNMTF.all_G

# Plot tau against iterations to see that it converges
f, axarr = plt.subplots(4, sharex=True)
x = range(1,len(taus)+1)
axarr[0].set_title('Convergence of values')
axarr[0].plot(x, taus)
axarr[0].set_ylabel("tau")
axarr[1].plot(x, Fs[:,0,0])    
axarr[1].set_ylabel("F[0,0]")
axarr[2].plot(x, Ss[:,0,0]) 
axarr[2].set_ylabel("S[0,0]")
axarr[3].plot(x, Gs[:,0,0]) 
axarr[3].set_ylabel("G[0,0]")
axarr[3].set_xlabel("Iterations")

# Approximate the expectations
burn_in = 500
thinning = 5
(exp_F, exp_S, exp_G, exp_tau) = BNMTF.approx_expectation(burn_in,thinning)

# Also measure the performances
performances = BNMTF.predict(M_test,burn_in,thinning)
print performances

