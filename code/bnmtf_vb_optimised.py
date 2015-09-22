"""
Variational Bayesian inference for non-negative matrix tri-factorisation.
We optimise the updates s.t. we compute each column of F and G using matrix
operations, rather than each element individually.

We expect the following arguments:
- R, the matrix
- M, the mask matrix indicating observed values (1) and unobserved ones (0)
- K, the number of row clusters
- L, the number of column clusters
- priors = { 'alpha' = alpha_R, 'beta' = beta_R, 'lambdaF' = [[lambdaFik]], 'lambdaS' = [[lambdaSkl]], 'lambdaG' = [[lambdaGjl]] },
    a dictionary defining the priors over tau, F, S, G.
    
Initialisation can be done by running the initialise(init_S,init_FG,tauFSG) function, with argument 
init_S for S, and init_FG for F and G:
- init_S = 'exp'        -> muS[k,l] = 1/lambdaS[k,l]
         = 'random'     -> muS[k,l] ~ Exp(lambdaS[k,l])
- init_FG = 'exp'       -> muF[i,k] = 1/lambdaF[i,k], muG[j,l] = 1/lambdaG[j,l]
          = 'random'    -> muF[i,k] ~ Exp(lambdaF[i,k]), muG[j,l] ~ Exp(lambdaG[j,l])
          = 'kmeans'    -> muF = KMeans(R,rows)+0.2, muG = KMeans(R,columns)+0.2
- tauF[i,k] = tauS[k,l] = tauG[j,l] = 1 if tauFSG = {}, else tauF = tauFSG['tauF'], etc.
- alpha_s, beta_s using updates of model


Usage of class:
    BNMF = bnmf_vb(R,M,K,L,priors)
    BNMF.initisalise(init_S,init_FG) 
    BNMF.run(iterations)
Or:
    BNMF = bnmf_vb(R,M,K,L,priors)
    BNMF.train(init_S,init_FG,iterations)
    
We can test the performance of our model on a test dataset, specifying our test set with a mask M. 
    performance = BNMF.predict(M_pred)
This gives a dictionary of performances,
    performance = { 'MSE', 'R^2', 'Rp' }
    
Finally, we can return the goodness of fit of the data using the quality(metric) function:
- metric = 'loglikelihood' -> return p(D|theta)
         = 'BIC'        -> return Bayesian Information Criterion
         = 'AIC'        -> return Afaike Information Criterion
         = 'MSE'        -> return Mean Square Error
(we want to maximise these values)
"""

import sys
sys.path.append("/home/tab43/Documents/Projects/libraries/")
from kmeans_missing.code.kmeans import KMeans

from distributions.gamma import Gamma
from distributions.truncated_normal import TruncatedNormal
from distributions.truncated_normal_vector import TruncatedNormalVector
from distributions.exponential import Exponential

import numpy, itertools, math, scipy, time
from scipy.stats import norm
import matplotlib.pyplot as plt

class bnmtf_vb_optimised:
    def __init__(self,R,M,K,L,priors):
        self.R = numpy.array(R,dtype=float)
        self.M = numpy.array(M,dtype=float)
        self.K = K
        self.L = L
        
        assert len(self.R.shape) == 2, "Input matrix R is not a two-dimensional array, " \
            "but instead %s-dimensional." % len(self.R.shape)
        assert self.R.shape == self.M.shape, "Input matrix R is not of the same size as " \
            "the indicator matrix M: %s and %s respectively." % (self.R.shape,self.M.shape)
            
        (self.I,self.J) = self.R.shape
        self.size_Omega = self.M.sum()
        self.check_empty_rows_columns()      
        
        self.alpha, self.beta, self.lambdaF, self.lambdaS, self.lambdaG = \
            float(priors['alpha']), float(priors['beta']), numpy.array(priors['lambdaF']), numpy.array(priors['lambdaS']), numpy.array(priors['lambdaG'])
        
        assert self.lambdaF.shape == (self.I,self.K), "Prior matrix lambdaF has the wrong shape: %s instead of (%s, %s)." % (self.lambdaF.shape,self.I,self.K)
        assert self.lambdaS.shape == (self.K,self.L), "Prior matrix lambdaS has the wrong shape: %s instead of (%s, %s)." % (self.lambdaS.shape,self.K,self.L)
        assert self.lambdaG.shape == (self.J,self.L), "Prior matrix lambdaG has the wrong shape: %s instead of (%s, %s)." % (self.lambdaG.shape,self.J,self.L)
                   
            
    # Raise an exception if an entire row or column is empty
    def check_empty_rows_columns(self):
        sums_columns = self.M.sum(axis=0)
        sums_rows = self.M.sum(axis=1)
                    
        # Assert none of the rows or columns are entirely unknown values
        for i,c in enumerate(sums_rows):
            assert c != 0, "Fully unobserved row in R, row %s." % i
        for j,c in enumerate(sums_columns):
            assert c != 0, "Fully unobserved column in R, column %s." % j


    # Initialise and run the sampler
    def train(self,init_S,init_FG,iterations):
        self.initialise(init_S,init_FG)
        return self.run(iterations)


    # Initialise U, V, and tau. 
    def initialise(self,init_S='random',init_FG='random',tauFSG={}):
        self.tauF = tauFSG['tauF'] if 'tauF' in tauFSG else numpy.ones((self.I,self.K))
        self.tauS = tauFSG['tauS'] if 'tauS' in tauFSG else numpy.ones((self.K,self.L))
        self.tauG = tauFSG['tauG'] if 'tauG' in tauFSG else numpy.ones((self.J,self.L))
        
        assert init_S in ['exp','random'], "Unrecognised init option for S: %s." % init_S
        self.muS = 1./self.lambdaS
        if init_S == 'random':
            for k,l in itertools.product(xrange(0,self.K),xrange(0,self.L)):  
                self.muS[k,l] = Exponential(self.lambdaS[k,l]).draw()
        
        assert init_FG in ['exp','random','kmeans'], "Unrecognised init option for F,G: %s." % init_FG
        self.muF, self.muG = 1./self.lambdaF, 1./self.lambdaG
        if init_FG == 'random':
            for i,k in itertools.product(xrange(0,self.I),xrange(0,self.K)):        
                self.muF[i,k] = Exponential(self.lambdaF[i,k]).draw()
            for j,l in itertools.product(xrange(0,self.J),xrange(0,self.L)):
                self.muG[j,l] = Exponential(self.lambdaG[j,l]).draw()
        elif init_FG == 'kmeans':
            print "Initialising F using KMeans."
            kmeans_F = KMeans(self.R,self.M,self.K)
            kmeans_F.initialise()
            kmeans_F.cluster()
            self.muF = kmeans_F.clustering_results #+ 0.2            
            
            print "Initialising G using KMeans."
            kmeans_G = KMeans(self.R.T,self.M.T,self.L)   
            kmeans_G.initialise()
            kmeans_G.cluster()
            self.muG = kmeans_G.clustering_results #+ 0.2
        
        # Initialise the expectations and variances
        self.expF, self.varF = numpy.zeros((self.I,self.K)), numpy.zeros((self.I,self.K))
        self.expS, self.varS = numpy.zeros((self.K,self.L)), numpy.zeros((self.K,self.L))
        self.expG, self.varG = numpy.zeros((self.J,self.L)), numpy.zeros((self.J,self.L))
        
        for k in range(0,self.K):
            self.update_exp_F(k)
        for k,l in itertools.product(xrange(0,self.K),xrange(0,self.L)):
            self.update_exp_S(k,l)
        for l in range(0,self.L):
            self.update_exp_G(l)
            
        # Initialise tau using the updates
        self.update_tau()
        self.update_exp_tau()


    # Run the Gibbs sampler
    def run(self,iterations):
        self.all_exp_tau = []  # to check for convergence     
        
        for it in range(0,iterations):         
            for k,l in itertools.product(xrange(0,self.K),xrange(0,self.L)):
                self.update_S(k,l)
                self.update_exp_S(k,l)
                
            self.update_tau()
            self.update_exp_tau()
            
            for k in range(0,self.K):
                self.update_F(k)
                self.update_exp_F(k)
                
            self.update_tau()
            self.update_exp_tau()
                
            for l in range(0,self.L):
                self.update_G(l)
                self.update_exp_G(l)
                
            self.update_tau()
            self.update_exp_tau()
            self.all_exp_tau.append(self.exptau)
            
            perf, elbo = self.predict(self.M), self.elbo()
            print "Iteration %s. ELBO: %s. MSE: %s. R^2: %s. Rp: %s." % (it+1,elbo,perf['MSE'],perf['R^2'],perf['Rp'])
                        
        
    # Compute the ELBO
    def elbo(self):
        return self.size_Omega / 2. * ( self.explogtau - math.log(2*math.pi) ) \
             - self.exptau / 2. * self.exp_square_diff() \
             + numpy.log(self.lambdaF).sum() - ( self.lambdaF * self.expF ).sum() \
             + numpy.log(self.lambdaS).sum() - ( self.lambdaS * self.expS ).sum() \
             + numpy.log(self.lambdaG).sum() - ( self.lambdaG * self.expG ).sum() \
             + self.alpha * math.log(self.beta) - scipy.special.gammaln(self.alpha) \
             + (self.alpha - 1.)*self.explogtau - self.beta * self.exptau \
             - self.alpha_s * math.log(self.beta_s) + scipy.special.gammaln(self.alpha_s) \
             - (self.alpha_s - 1.)*self.explogtau + self.beta_s * self.exptau \
             - .5*numpy.log(self.tauF).sum() + self.I*self.K/2.*math.log(2*math.pi) \
             + numpy.log(0.5*scipy.special.erfc(-self.muF*numpy.sqrt(self.tauF)/math.sqrt(2))).sum() \
             + ( self.tauF / 2. * ( self.varF + (self.expF - self.muF)**2 ) ).sum() \
             - .5*numpy.log(self.tauS).sum() + self.K*self.L/2.*math.log(2*math.pi) \
             + numpy.log(0.5*scipy.special.erfc(-self.muS*numpy.sqrt(self.tauS)/math.sqrt(2))).sum() \
             + ( self.tauS / 2. * ( self.varS + (self.expS - self.muS)**2 ) ).sum() \
             - .5*numpy.log(self.tauG).sum() + self.J*self.L/2.*math.log(2*math.pi) \
             + numpy.log(0.5*scipy.special.erfc(-self.muG*numpy.sqrt(self.tauG)/math.sqrt(2))).sum() \
             + ( self.tauG / 2. * ( self.varG + (self.expG - self.muG)**2 ) ).sum()
        

    # Compute the dot product of three matrices
    def triple_dot(self,M1,M2,M3):
        return numpy.dot(M1,numpy.dot(M2,M3))
        
        
    # Update the parameters for the distributions
    def update_tau(self):   
        self.alpha_s = self.alpha + self.size_Omega/2.0
        self.beta_s = self.beta + 0.5*self.exp_square_diff()
        
    def exp_square_diff(self): # Compute: sum_Omega E_q(F,S,G) [ ( Rij - Fi S Gj )^2 ]
        return (self.M*( self.R - self.triple_dot(self.expF,self.expS,self.expG.T) )**2).sum() + \
               (self.M*( self.triple_dot(self.varF+self.expF**2, self.varS+self.expS**2, (self.varG+self.expG**2).T ) - self.triple_dot(self.expF**2,self.expS**2,(self.expG**2).T) )).sum() + \
               (self.M*( numpy.dot(self.varF, ( numpy.dot(self.expS,self.expG.T)**2 - numpy.dot(self.expS**2,self.expG.T**2) ) ) )).sum() + \
               (self.M*( numpy.dot( numpy.dot(self.expF,self.expS)**2 - numpy.dot(self.expF**2,self.expS**2), self.varG.T ) )).sum()
    
    def update_F(self,k):  
        varSkG = numpy.dot( self.varS[k]+self.expS[k]**2 , (self.varG+self.expG**2).T ) - numpy.dot( self.expS[k]**2 , (self.expG**2).T ) # Vector of size J
        self.tauF[:,k] = self.exptau*( self.M * ( varSkG + ( numpy.dot(self.expS[k],self.expG.T) )**2 ) ).sum(axis=1)  #sum over j, so rows
        self.muF[:,k] = 1./self.tauF[:,k] * (
            - self.lambdaF[:,k]
            + self.exptau*( self.M * ( (self.R-self.triple_dot(self.expF,self.expS,self.expG.T)+numpy.outer(self.expF[:,k],numpy.dot(self.expS[k],self.expG.T)) ) * numpy.dot(self.expS[k],self.expG.T) )).sum(axis=1)
            - self.exptau*( self.M * ( ( numpy.dot(self.expS[k]*numpy.dot(self.expF,self.expS), self.varG.T) - numpy.outer(self.expF[:,k], numpy.dot( self.expS[k]**2, self.varG.T )) ) ) ).sum(axis=1)
        ) 
        
    def update_S(self,k,l):       
        self.tauS[k,l] = self.exptau*(self.M*( numpy.outer( self.varF[:,k]+self.expF[:,k]**2 , self.varG[:,l]+self.expG[:,l]**2 ) )).sum()
        self.muS[k,l] = 1./self.tauS[k,l] * (
            - self.lambdaS[k,l] 
            + self.exptau*(self.M * ( (self.R-self.triple_dot(self.expF,self.expS,self.expG.T)+self.expS[k,l]*numpy.outer(self.expF[:,k],self.expG[:,l]) ) * numpy.outer(self.expF[:,k],self.expG[:,l]) )).sum()
            - self.exptau*(self.M * numpy.outer( self.expF[:,k] * ( numpy.dot(self.expF,self.expS[:,l]) - self.expF[:,k]*self.expS[k,l] ), self.varG[:,l] )).sum()
            - self.exptau*(self.M * numpy.outer( self.varF[:,k], self.expG[:,l]*(numpy.dot(self.expS[k],self.expG.T) - self.expS[k,l]*self.expG[:,l]) )).sum()
        ) 
        
    def update_G(self,l):  
        varFSl = numpy.dot( self.varF+self.expF**2 , self.varS[:,l]+self.expS[:,l]**2 ) - numpy.dot( self.expF**2 , self.expS[:,l]**2 ) # Vector of size I
        self.tauG[:,l] = self.exptau*(self.M.T * ( varFSl + ( numpy.dot(self.expF,self.expS[:,l]) )**2 )).T.sum(axis=0) #sum over i, so columns        
        self.muG[:,l] = 1./self.tauG[:,l] * (
            - self.lambdaG[:,l] 
            + self.exptau * (self.M * ( (self.R-self.triple_dot(self.expF,self.expS,self.expG.T)+numpy.outer(numpy.dot(self.expF,self.expS[:,l]), self.expG[:,l]) ).T * numpy.dot(self.expF,self.expS[:,l]) ).T ).sum(axis=0)
            - self.exptau * (self.M * ( numpy.dot(self.varF, (self.expS[:,l]*numpy.dot(self.expS,self.expG.T).T).T) - numpy.outer(numpy.dot(self.varF,self.expS[:,l]**2), self.expG[:,l]) )).sum(axis=0)
        )

    # Update the expectations and variances
    def update_exp_F(self,k):
        tn = TruncatedNormalVector(self.muF[:,k],self.tauF[:,k])
        self.expF[:,k] = tn.expectation()
        self.varF[:,k] = tn.variance()
        
    def update_exp_S(self,k,l):
        tn = TruncatedNormal(self.muS[k,l],self.tauS[k,l])
        self.expS[k,l] = tn.expectation()
        self.varS[k,l] = tn.variance()
        
    def update_exp_G(self,l):
        tn = TruncatedNormalVector(self.muG[:,l],self.tauG[:,l])
        self.expG[:,l] = tn.expectation()
        self.varG[:,l] = tn.variance()
        
    def update_exp_tau(self):
        gm = Gamma(self.alpha_s,self.beta_s)
        self.exptau = gm.expectation()
        self.explogtau = gm.expectation_log()


    # Compute the expectation of U and V, and use it to predict missing values
    def predict(self,M_pred):
        R_pred = self.triple_dot(self.expF,self.expS,self.expG.T)
        MSE = self.compute_MSE(M_pred,self.R,R_pred)
        R2 = self.compute_R2(M_pred,self.R,R_pred)    
        Rp = self.compute_Rp(M_pred,self.R,R_pred)        
        return {'MSE':MSE,'R^2':R2,'Rp':Rp}
        
        
    # Functions for computing MSE, R^2 (coefficient of determination), Rp (Pearson correlation)
    def compute_MSE(self,M,R,R_pred):
        return (M * (R-R_pred)**2).sum() / float(M.sum())
        
    def compute_R2(self,M,R,R_pred):
        mean = (M*R).sum() / float(M.sum())
        SS_total = float((M*(R-mean)**2).sum())
        SS_res = float((M*(R-R_pred)**2).sum())
        return 1. - SS_res / SS_total if SS_total != 0. else numpy.inf
        
    def compute_Rp(self,M,R,R_pred):
        mean_real = (M*R).sum() / float(M.sum())
        mean_pred = (M*R_pred).sum() / float(M.sum())
        covariance = (M*(R-mean_real)*(R_pred-mean_pred)).sum()
        variance_real = (M*(R-mean_real)**2).sum()
        variance_pred = (M*(R_pred-mean_pred)**2).sum()
        return covariance / float(math.sqrt(variance_real)*math.sqrt(variance_pred))
        
        
    # Functions for model selection, measuring the goodness of fit vs model complexity
    def quality(self,metric):
        assert metric in ['loglikelihood','BIC','AIC','MSE'], 'Unrecognised metric for model quality: %s.' % metric
        log_likelihood = self.log_likelihood()
        if metric == 'loglikelihood':
            return log_likelihood
        elif metric == 'BIC':
            # -2*loglikelihood + (no. free parameters * log(no data points))
            return log_likelihood - 0.5 * (self.I*self.K+self.K*self.L+self.J*self.L) * math.log(self.size_Omega)
        elif metric == 'AIC':
            # -2*loglikelihood + 2*no. free parameters
            return log_likelihood - (self.I*self.K+self.K*self.L+self.J*self.L)
        elif metric == 'MSE':
            R_pred = self.triple_dot(self.expF,self.expS,self.expG.T)
            return self.compute_MSE(self.M,self.R,R_pred)
        
    def log_likelihood(self):
        # Return the likelihood of the data given the trained model's parameters
        return self.size_Omega / 2. * ( self.explogtau - math.log(2*math.pi) ) \
             - self.exptau / 2. * (self.M*( self.R - self.triple_dot(self.expF,self.expS,self.expG.T) )**2).sum()