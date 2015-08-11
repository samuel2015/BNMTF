"""
Generate a toy dataset for the matrix tri-factorisation case, and store it.

We use dimensions 100 by 50 for the dataset, 10 row clusters, and 5 column clusters.

As the prior for F, G we take value 1 for all entries (so exp 1), and for S value 2 (so exp 1/2).

As a result, each value in R has a value of around 25, and a variance of .

For contrast, the Sanger dataset is as follows:
    Shape: (622,139). Fraction observed: 0.811307224317. 
    Mean: 11.9726909789. Variance: 34.1503768785. Maximum: 23.5959612058.

We add Gaussian noise of precision tau = 1 (prior for gamma: alpha=1,beta=1).
(Simply using the expectation of our Gamma distribution over tau)
"""

project_location = "/home/tab43/Documents/Projects/libraries/"
import sys
sys.path.append(project_location)

from BNMTF.code.distributions.exponential import Exponential
from BNMTF.code.distributions.normal import Normal
from ml_helpers.code.mask import generate_M

import numpy, itertools

def generate_dataset(I,J,K,L,lambdaF,lambdaS,lambdaG,tau):
    # Generate U, V
    F = numpy.zeros((I,K))
    for i,k in itertools.product(xrange(0,I),xrange(0,K)):
        F[i,k] = Exponential(lambdaF[i,k]).draw()
    S = numpy.zeros((K,L))
    for k,l in itertools.product(xrange(0,K),xrange(0,L)):
        S[k,l] = Exponential(lambdaS[k,l]).draw()
    G = numpy.zeros((J,L))
    for j,l in itertools.product(xrange(0,J),xrange(0,L)):
        G[j,l] = Exponential(lambdaG[j,l]).draw()
    
    # Generate R
    true_R = numpy.dot(F,numpy.dot(S,G.T))
    
    R = numpy.zeros((I,J))
    for i,j in itertools.product(xrange(0,I),xrange(0,J)):
        R[i,j] = Normal(true_R[i,j],tau).draw()   
        
    return (F,S,G,tau,true_R,R)
    
def add_noise(true_R,tau):
    (I,J) = true_R.shape
    R = numpy.zeros((I,J))
    for i,j in itertools.product(xrange(0,I),xrange(0,J)):
        R[i,j] = Normal(true_R[i,j],tau).draw()
    return R
    
##########

if __name__ == "__main__":
    output_folder = project_location+"BNMTF/example/generate_toy/bnmtf/"

    I,J,K,L = 100, 50, 10, 5
    fraction_unknown = 0.1
    alpha, beta = 1., 1.
    lambdaF = numpy.ones((I,K))
    lambdaS = numpy.ones((K,L))*2.
    lambdaG = numpy.ones((J,L))
    tau = alpha / beta
    
    (F,S,G,tau,true_R,R) = generate_dataset(I,J,K,L,lambdaF,lambdaS,lambdaG,tau)
    M = generate_M(I,J,fraction_unknown)
    
    # Store all matrices in text files
    numpy.savetxt(open(output_folder+"F.txt",'w'),F)
    numpy.savetxt(open(output_folder+"S.txt",'w'),S)
    numpy.savetxt(open(output_folder+"G.txt",'w'),G)
    numpy.savetxt(open(output_folder+"R_true.txt",'w'),true_R)
    numpy.savetxt(open(output_folder+"R.txt",'w'),R)
    numpy.savetxt(open(output_folder+"M.txt",'w'),M)
    
    print "Mean R: %s. Variance R: %s. Min R: %s. Max R: %s." % (numpy.mean(R),numpy.var(R),R.min(),R.max())